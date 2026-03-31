"""Prompt-based OCR — extract text from images using the VLM.

Rather than shipping a separate OCR engine (Tesseract, EasyOCR, …)
we re-use the already-loaded Vision Language Model.  This keeps the
memory footprint minimal — critical on phones with 1–2 GB RAM.

The VLM is prompted to list every piece of visible text together with
its approximate screen position and language.  The raw response is
then parsed into a list of :class:`~atlas_sight.data.models.TextBlock`
objects.
"""
from __future__ import annotations

import abc
import logging
import re
from dataclasses import dataclass

from atlas_sight.data.models import BoundingBox, TextBlock
from atlas_sight.vision.vlm import VisionLMBase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_OCR_PROMPT = (
    "List ALL visible text in this image. For each piece of text, provide:\n"
    "- The exact text content\n"
    "- Its position (top-left, top-center, top-right, center-left, center, "
    "center-right, bottom-left, bottom-center, bottom-right)\n"
    "- The language if it is not English\n\n"
    "Format each entry on its own line as:\n"
    'TEXT: "<content>" | POSITION: <position> | LANG: <language>\n\n'
    "If no text is visible, respond with: NO_TEXT_FOUND"
)

# ---------------------------------------------------------------------------
# Position → rough bounding-box mapping
# ---------------------------------------------------------------------------

_POSITION_BBOX: dict[str, BoundingBox] = {
    "top-left":      BoundingBox(0.00, 0.00, 0.33, 0.33),
    "top-center":    BoundingBox(0.33, 0.00, 0.66, 0.33),
    "top-right":     BoundingBox(0.66, 0.00, 1.00, 0.33),
    "center-left":   BoundingBox(0.00, 0.33, 0.33, 0.66),
    "center":        BoundingBox(0.33, 0.33, 0.66, 0.66),
    "center-right":  BoundingBox(0.66, 0.33, 1.00, 0.66),
    "bottom-left":   BoundingBox(0.00, 0.66, 0.33, 1.00),
    "bottom-center": BoundingBox(0.33, 0.66, 0.66, 1.00),
    "bottom-right":  BoundingBox(0.66, 0.66, 1.00, 1.00),
}

# Regex to parse one structured line from the VLM response.
_LINE_RE = re.compile(
    r'TEXT:\s*"(?P<text>[^"]+)"\s*\|\s*POSITION:\s*(?P<pos>[a-z\-]+)'
    r'(?:\s*\|\s*LANG:\s*(?P<lang>\w+))?',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class TextReaderBase(abc.ABC):
    """Interface for text-extraction backends."""

    @abc.abstractmethod
    async def read(self, image: bytes) -> list[TextBlock]:
        """Extract text blocks from *image* (JPEG/PNG bytes)."""

    @abc.abstractmethod
    async def load_model(self) -> None:
        """Initialise any required models or resources."""


# ---------------------------------------------------------------------------
# Concrete implementation — VLM-backed OCR
# ---------------------------------------------------------------------------


class TextReader(TextReaderBase):
    """Extract text from images by prompting the VLM.

    This is designed for reading signs, labels, menus, medicine bottles,
    and other real-world text encountered by a blind user.

    Parameters
    ----------
    vlm:
        A loaded :class:`VisionLMBase` instance.
    confidence_threshold:
        Minimum confidence to include a text block in the results.
        Because the VLM does not return per-block scores we assign a
        heuristic confidence based on text length and parsability.
    """

    def __init__(
        self,
        vlm: VisionLMBase,
        confidence_threshold: float = 0.5,
    ) -> None:
        self._vlm = vlm
        self._confidence_threshold = confidence_threshold

    # -- public API ---------------------------------------------------------

    async def read(self, image: bytes) -> list[TextBlock]:
        """Prompt the VLM and return structured text blocks."""
        if not self._vlm.is_loaded:
            logger.warning("VLM not loaded — OCR unavailable")
            return []

        response = await self._vlm.answer(image, _OCR_PROMPT)
        blocks = self._parse_vlm_response(response)
        return [b for b in blocks if b.confidence >= self._confidence_threshold]

    async def load_model(self) -> None:
        """Delegate to the underlying VLM."""
        await self._vlm.load_model()

    # -- parsing ------------------------------------------------------------

    def _parse_vlm_response(self, response: str) -> list[TextBlock]:
        """Turn the VLM's structured text into :class:`TextBlock` objects.

        The parser is intentionally lenient — if the VLM deviates from
        the requested format we still try to salvage useful text.
        """
        if not response or "NO_TEXT_FOUND" in response.upper():
            return []

        blocks: list[TextBlock] = []

        # First pass: try the structured regex format
        for match in _LINE_RE.finditer(response):
            text = match.group("text").strip()
            pos = match.group("pos").strip().lower()
            lang = (match.group("lang") or "en").strip().lower()

            if not text:
                continue

            bbox = _POSITION_BBOX.get(pos)
            confidence = self._heuristic_confidence(text, structured=True)
            blocks.append(TextBlock(
                text=text,
                confidence=confidence,
                bbox=bbox,
                language=lang,
            ))

        if blocks:
            return blocks

        # Fallback: the VLM may have returned a free-form list.
        # Treat each non-empty line as a text block.
        for line in response.splitlines():
            line = line.strip().lstrip("-•*0123456789.) ")
            if not line or len(line) < 2:
                continue
            confidence = self._heuristic_confidence(line, structured=False)
            blocks.append(TextBlock(
                text=line,
                confidence=confidence,
                bbox=None,
                language="en",
            ))

        return blocks

    @staticmethod
    def _heuristic_confidence(text: str, *, structured: bool) -> float:
        """Assign a rough confidence score to extracted text.

        Structured matches (parsed via the regex) get a base score of
        0.75; free-form fallback lines get 0.45.  Longer text is
        slightly penalised (VLMs hallucinate more on long strings).
        """
        base = 0.75 if structured else 0.45
        length = len(text)
        if length > 200:
            base -= 0.15
        elif length > 100:
            base -= 0.05
        return round(max(0.1, min(1.0, base)), 2)
