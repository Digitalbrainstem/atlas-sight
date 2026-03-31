"""SceneAnalyzer — builds a complete Scene from vision outputs."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from atlas_sight.config import Verbosity
from atlas_sight.data.models import DetectedObject, Obstacle, Scene, TextBlock

if TYPE_CHECKING:
    from atlas_sight.navigation.obstacle import ObstacleWarner
    from atlas_sight.vision.detector import ObjectDetectorBase
    from atlas_sight.vision.ocr import TextReaderBase
    from atlas_sight.vision.vlm import VisionLMBase

logger = logging.getLogger(__name__)


class SceneAnalyzer:
    """Builds a complete :class:`Scene` by fusing VLM, OCR, and detector output.

    The heavy lifting (VLM description + object detection) runs concurrently
    via :func:`asyncio.gather`.  Secondary tasks (OCR, obstacle classification)
    are best-effort — a failure never blocks the primary scene description.
    """

    def __init__(
        self,
        vlm: VisionLMBase,
        ocr: TextReaderBase,
        detector: ObjectDetectorBase,
        obstacle_warner: ObstacleWarner,
    ) -> None:
        self._vlm = vlm
        self._ocr = ocr
        self._detector = detector
        self._obstacle_warner = obstacle_warner

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        image: bytes,
        verbosity: Verbosity = Verbosity.NORMAL,
        context: str = "",
    ) -> Scene:
        """Run VLM + detector concurrently, combine into a single Scene.

        Parameters
        ----------
        image:
            Raw frame bytes from the camera.
        verbosity:
            Controls how much detail the VLM should include.
        context:
            Optional context string from :class:`ContextTracker` so the VLM
            can focus on what changed.
        """
        prompt = self._build_prompt(verbosity, context)

        # Primary tasks — run concurrently
        description_result, detection_result = await asyncio.gather(
            self._vlm.describe(image, prompt=prompt),
            self._detector.detect(image),
            return_exceptions=True,
        )

        # Graceful degradation — a blind person still needs *something*
        if isinstance(description_result, BaseException):
            logger.error("VLM description failed: %s", description_result)
            description: str = (
                "I'm having trouble describing the scene right now."
            )
        else:
            description = description_result

        if isinstance(detection_result, BaseException):
            logger.error("Object detection failed: %s", detection_result)
            objects: list[DetectedObject] = []
        else:
            objects = detection_result

        # Secondary tasks — best-effort, never block the response
        text_blocks = await self._safe_read_text(image)
        obstacles = await self._safe_classify_obstacles(objects)

        return self._merge_results(
            description=description,
            objects=objects,
            text_blocks=text_blocks,
            obstacles=obstacles,
            detail_level=verbosity.value,
            raw_image=image,
        )

    async def analyze_text(self, image: bytes) -> list[TextBlock]:
        """OCR-focused analysis of a single frame."""
        return await self._safe_read_text(image)

    async def analyze_obstacles(self, image: bytes) -> list[Obstacle]:
        """Detection + obstacle classification for a single frame."""
        try:
            objects = await self._detector.detect(image)
            return await self._obstacle_warner.classify(objects)
        except Exception:
            logger.error("Obstacle analysis failed", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(verbosity: Verbosity, context: str) -> str:
        """Build the VLM prompt, optionally including recent context.

        The prompt tells the model *how much* detail we want and gives it
        the last few descriptions so it can emphasise what changed.
        """
        if verbosity == Verbosity.BRIEF:
            base = (
                "Describe this scene in one short sentence for a visually "
                "impaired person.  Focus only on the most important element."
            )
        elif verbosity == Verbosity.DETAILED:
            base = (
                "Describe this scene in detail for a visually impaired "
                "person.  Include spatial relationships, colours, text, "
                "people, and obstacles.  Be thorough but natural."
            )
        else:
            base = (
                "Describe this scene for a visually impaired person.  "
                "Mention key objects, people, text, and any obstacles "
                "or hazards."
            )

        parts: list[str] = [base]
        if context:
            parts.append(context)
            parts.append("Focus on what has changed or what is new.")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_results(
        description: str,
        objects: list[DetectedObject],
        text_blocks: list[TextBlock],
        obstacles: list[Obstacle],
        detail_level: str = "normal",
        raw_image: bytes | None = None,
    ) -> Scene:
        """Combine all analysis outputs into a single :class:`Scene`."""
        return Scene(
            description=description,
            objects=objects,
            text_blocks=text_blocks,
            obstacles=obstacles,
            timestamp=time.time(),
            detail_level=detail_level,
            raw_image=raw_image,
        )

    # ------------------------------------------------------------------
    # Safe wrappers (never raise)
    # ------------------------------------------------------------------

    async def _safe_read_text(self, image: bytes) -> list[TextBlock]:
        """Run OCR, returning an empty list on failure."""
        try:
            return await self._ocr.read(image)
        except Exception:
            logger.warning("OCR failed, continuing without text", exc_info=True)
            return []

    async def _safe_classify_obstacles(
        self,
        objects: list[DetectedObject],
    ) -> list[Obstacle]:
        """Classify detected objects into obstacles, returning [] on failure."""
        try:
            return await self._obstacle_warner.classify(objects)
        except Exception:
            logger.warning("Obstacle classification failed", exc_info=True)
            return []
