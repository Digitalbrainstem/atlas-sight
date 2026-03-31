"""Prompt-based object detection — detect and locate objects using the VLM.

Like :mod:`atlas_sight.vision.ocr`, this module re-uses the loaded
Vision Language Model instead of shipping a dedicated detector (YOLO,
SSD, …).  The VLM is prompted to list objects it sees along with their
approximate positions and sizes, which we parse into
:class:`~atlas_sight.data.models.DetectedObject` instances.
"""
from __future__ import annotations

import abc
import logging
import re
from dataclasses import dataclass

from atlas_sight.data.models import (
    BoundingBox,
    DetectedObject,
    ObjectCategory,
)
from atlas_sight.vision.vlm import VisionLMBase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

CATEGORY_MAP: dict[str, ObjectCategory] = {
    # People
    "person": ObjectCategory.PERSON,
    "man": ObjectCategory.PERSON,
    "woman": ObjectCategory.PERSON,
    "child": ObjectCategory.PERSON,
    "baby": ObjectCategory.PERSON,
    "pedestrian": ObjectCategory.PERSON,
    # Vehicles
    "car": ObjectCategory.VEHICLE,
    "truck": ObjectCategory.VEHICLE,
    "bus": ObjectCategory.VEHICLE,
    "bicycle": ObjectCategory.VEHICLE,
    "bike": ObjectCategory.VEHICLE,
    "motorcycle": ObjectCategory.VEHICLE,
    "scooter": ObjectCategory.VEHICLE,
    "wheelchair": ObjectCategory.VEHICLE,
    "stroller": ObjectCategory.VEHICLE,
    # Furniture
    "chair": ObjectCategory.FURNITURE,
    "table": ObjectCategory.FURNITURE,
    "desk": ObjectCategory.FURNITURE,
    "couch": ObjectCategory.FURNITURE,
    "sofa": ObjectCategory.FURNITURE,
    "bench": ObjectCategory.FURNITURE,
    "bed": ObjectCategory.FURNITURE,
    "shelf": ObjectCategory.FURNITURE,
    "cabinet": ObjectCategory.FURNITURE,
    # Doors / openings
    "door": ObjectCategory.DOOR,
    "gate": ObjectCategory.DOOR,
    "doorway": ObjectCategory.DOOR,
    "entrance": ObjectCategory.DOOR,
    "exit": ObjectCategory.DOOR,
    # Stairs / steps
    "stairs": ObjectCategory.STAIRS,
    "staircase": ObjectCategory.STAIRS,
    "step": ObjectCategory.STAIRS,
    "steps": ObjectCategory.STAIRS,
    "escalator": ObjectCategory.STAIRS,
    "ramp": ObjectCategory.STAIRS,
    # Obstacles
    "pole": ObjectCategory.OBSTACLE,
    "bollard": ObjectCategory.OBSTACLE,
    "cone": ObjectCategory.OBSTACLE,
    "barrier": ObjectCategory.OBSTACLE,
    "fence": ObjectCategory.OBSTACLE,
    "wall": ObjectCategory.OBSTACLE,
    "curb": ObjectCategory.OBSTACLE,
    "pothole": ObjectCategory.OBSTACLE,
    "rock": ObjectCategory.OBSTACLE,
    "trash can": ObjectCategory.OBSTACLE,
    "fire hydrant": ObjectCategory.OBSTACLE,
    # Signs
    "sign": ObjectCategory.SIGN,
    "traffic sign": ObjectCategory.SIGN,
    "street sign": ObjectCategory.SIGN,
    "stop sign": ObjectCategory.SIGN,
    "traffic light": ObjectCategory.SIGN,
    # Animals
    "dog": ObjectCategory.ANIMAL,
    "cat": ObjectCategory.ANIMAL,
    "bird": ObjectCategory.ANIMAL,
    "animal": ObjectCategory.ANIMAL,
    # Food
    "food": ObjectCategory.FOOD,
    "bottle": ObjectCategory.FOOD,
    "cup": ObjectCategory.FOOD,
    "plate": ObjectCategory.FOOD,
    "bowl": ObjectCategory.FOOD,
    # Electronics
    "phone": ObjectCategory.ELECTRONIC,
    "laptop": ObjectCategory.ELECTRONIC,
    "computer": ObjectCategory.ELECTRONIC,
    "television": ObjectCategory.ELECTRONIC,
    "tv": ObjectCategory.ELECTRONIC,
    "monitor": ObjectCategory.ELECTRONIC,
    "screen": ObjectCategory.ELECTRONIC,
}

# ---------------------------------------------------------------------------
# Detection prompt
# ---------------------------------------------------------------------------

_DETECT_PROMPT = (
    "List ALL objects you can see in this image. For each object provide:\n"
    "- Object name (single common noun or short phrase)\n"
    "- Approximate position as normalised coordinates (x_min, y_min, x_max, "
    "y_max) where 0.0 is top-left and 1.0 is bottom-right\n"
    "- Size: small / medium / large\n\n"
    "Format each entry on its own line as:\n"
    "OBJ: <name> | BBOX: <x_min>, <y_min>, <x_max>, <y_max> | SIZE: <size>\n\n"
    "If the image is blank or you cannot identify objects, respond with: "
    "NO_OBJECTS_FOUND"
)

# Regex for structured lines
_OBJ_RE = re.compile(
    r"OBJ:\s*(?P<name>[^|]+?)\s*\|\s*BBOX:\s*"
    r"(?P<x1>[\d.]+)\s*,\s*(?P<y1>[\d.]+)\s*,\s*"
    r"(?P<x2>[\d.]+)\s*,\s*(?P<y2>[\d.]+)\s*"
    r"(?:\|\s*SIZE:\s*(?P<size>\w+))?",
    re.IGNORECASE,
)

# Rough size→distance heuristic (bbox area %).  Larger area ≈ closer.
_SIZE_DISTANCE: dict[str, float] = {
    "large": 0.8,
    "medium": 2.5,
    "small": 5.0,
}


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class ObjectDetectorBase(abc.ABC):
    """Interface for object-detection backends."""

    @abc.abstractmethod
    async def detect(self, image: bytes) -> list[DetectedObject]:
        """Detect objects in *image* (JPEG/PNG bytes)."""

    @abc.abstractmethod
    async def load_model(self) -> None:
        """Initialise any required models or resources."""


# ---------------------------------------------------------------------------
# Concrete implementation — VLM-backed detector
# ---------------------------------------------------------------------------


class ObjectDetector(ObjectDetectorBase):
    """Detect objects by prompting the VLM.

    Parameters
    ----------
    vlm:
        A loaded :class:`VisionLMBase` instance.
    confidence_threshold:
        Minimum confidence to keep a detection.  Structured-format
        detections get higher heuristic confidence than free-form ones.
    """

    def __init__(
        self,
        vlm: VisionLMBase,
        confidence_threshold: float = 0.4,
    ) -> None:
        self._vlm = vlm
        self._confidence_threshold = confidence_threshold

    # -- public API ---------------------------------------------------------

    async def detect(self, image: bytes) -> list[DetectedObject]:
        """Prompt the VLM and return detected objects."""
        if not self._vlm.is_loaded:
            logger.warning("VLM not loaded — object detection unavailable")
            return []

        response = await self._vlm.answer(image, _DETECT_PROMPT)
        detections = self._parse_detections(response)
        return [d for d in detections if d.confidence >= self._confidence_threshold]

    async def load_model(self) -> None:
        """Delegate to the underlying VLM."""
        await self._vlm.load_model()

    # -- parsing ------------------------------------------------------------

    def _parse_detections(self, response: str) -> list[DetectedObject]:
        """Parse the VLM response into :class:`DetectedObject` list.

        Tries the structured format first, then falls back to
        free-form line-by-line extraction.
        """
        if not response or "NO_OBJECTS_FOUND" in response.upper():
            return []

        detections: list[DetectedObject] = []

        # Structured format
        for match in _OBJ_RE.finditer(response):
            name = match.group("name").strip().lower()
            size = (match.group("size") or "medium").strip().lower()
            if not name:
                continue

            bbox = self._safe_bbox(
                match.group("x1"),
                match.group("y1"),
                match.group("x2"),
                match.group("y2"),
            )
            if bbox is None:
                continue

            category = self._classify_category(name)
            distance = self._estimate_distance_from_size(size, bbox)
            confidence = self._heuristic_confidence(name, bbox, structured=True)

            detections.append(DetectedObject(
                label=name,
                confidence=confidence,
                bbox=bbox,
                category=category,
                distance_m=distance,
            ))

        if detections:
            return detections

        # Fallback: treat each line as an object name
        for line in response.splitlines():
            line = line.strip().lstrip("-•*0123456789.) ")
            if not line or len(line) < 2 or len(line) > 60:
                continue

            name = line.lower()
            category = self._classify_category(name)
            bbox = BoundingBox(0.0, 0.0, 1.0, 1.0)  # unknown position
            confidence = self._heuristic_confidence(name, bbox, structured=False)

            detections.append(DetectedObject(
                label=name,
                confidence=confidence,
                bbox=bbox,
                category=category,
                distance_m=None,
            ))

        return detections

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _safe_bbox(
        x1: str, y1: str, x2: str, y2: str
    ) -> BoundingBox | None:
        """Parse and clamp four coordinate strings into a BoundingBox."""
        try:
            coords = [float(x1), float(y1), float(x2), float(y2)]
        except (ValueError, TypeError):
            return None

        # Clamp to [0, 1]
        coords = [max(0.0, min(1.0, c)) for c in coords]
        x_min, y_min, x_max, y_max = coords

        # Ensure min < max
        if x_min >= x_max or y_min >= y_max:
            return None

        return BoundingBox(x_min, y_min, x_max, y_max)

    @staticmethod
    def _classify_category(label: str) -> ObjectCategory:
        """Map an object label to an :class:`ObjectCategory`.

        Tries exact match first, then checks whether any known key
        appears as a substring in the label.
        """
        normalised = label.strip().lower()

        # Exact match
        if normalised in CATEGORY_MAP:
            return CATEGORY_MAP[normalised]

        # Substring match (e.g. "traffic sign" → SIGN)
        for key, cat in CATEGORY_MAP.items():
            if key in normalised:
                return cat

        return ObjectCategory.OTHER

    @staticmethod
    def _estimate_distance(obj: DetectedObject) -> float | None:
        """Rough distance estimate from bounding-box area.

        Uses a simple inverse-proportional heuristic: objects that
        occupy more of the frame are assumed to be closer.  This is
        *not* depth estimation — just a coarse guide for the haptic
        and voice layers to prioritise nearer objects.

        Returns ``None`` if the bbox area is zero or negligible.
        """
        area = obj.bbox.area
        if area < 0.001:
            return None

        # area ≈ 0.5 → ~0.5 m (very close / large)
        # area ≈ 0.01 → ~5 m (far away / small)
        return round(max(0.3, min(10.0, 0.25 / (area ** 0.5))), 1)

    @staticmethod
    def _estimate_distance_from_size(
        size: str, bbox: BoundingBox
    ) -> float | None:
        """Combine the VLM's size label with bbox area for a distance guess."""
        # Prefer the explicit size hint if available
        base = _SIZE_DISTANCE.get(size.lower())
        if base is not None:
            # Refine slightly with actual area
            area = bbox.area
            if area > 0.001:
                area_estimate = max(0.3, min(10.0, 0.25 / (area ** 0.5)))
                return round((base + area_estimate) / 2, 1)
            return base

        # No size hint — fall back to pure area heuristic
        area = bbox.area
        if area < 0.001:
            return None
        return round(max(0.3, min(10.0, 0.25 / (area ** 0.5))), 1)

    @staticmethod
    def _heuristic_confidence(
        label: str, bbox: BoundingBox, *, structured: bool
    ) -> float:
        """Assign a heuristic confidence to a detection.

        Structured detections (with valid bboxes from the regex) are
        more trustworthy than free-form fallback lines.
        """
        base = 0.70 if structured else 0.35

        # Known categories get a small boost
        if label.strip().lower() in CATEGORY_MAP:
            base += 0.10

        # Suspiciously tiny or full-frame boxes get penalised
        area = bbox.area
        if area < 0.005 or area > 0.95:
            base -= 0.10

        return round(max(0.1, min(1.0, base)), 2)
