"""Read mode — find and read text visible to the camera.

Handles signs, labels, menus, medicine bottles, and any other printed or
displayed text.  Uses the OCR engine for raw text extraction and the VLM
for semantically guided reading ("read the menu", "read the sign").
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from atlas_sight.data.models import Scene, TextBlock
from atlas_sight.interaction.audio_cues import AudioCues
from atlas_sight.interaction.haptics import HapticFeedback
from atlas_sight.modes.base import ModeBase
from atlas_sight.vision.camera import CameraManager
from atlas_sight.vision.ocr import TextReaderBase
from atlas_sight.vision.vlm import VisionLMBase
from atlas_sight.voice.speaker import Speaker

logger = logging.getLogger(__name__)

_NO_TEXT_MESSAGE = (
    "I don't see any text. "
    "Try pointing the camera at a sign or label."
)


@dataclass
class ReadMode(ModeBase):
    """Find and read text in the environment for the user."""

    camera: CameraManager = field(repr=False)
    vlm: VisionLMBase = field(repr=False)
    ocr: TextReaderBase = field(repr=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def activate(self) -> None:
        await self.haptics.pulse()
        await self._announce("Read mode. Point the camera at text.")
        self._active = True
        logger.info("Read mode activated")

    async def deactivate(self) -> None:
        self._active = False
        logger.info("Read mode deactivated")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def read_text(self) -> list[TextBlock]:
        """Capture a frame, run OCR, and speak all detected text.

        Returns the list of :class:`TextBlock` objects found (may be empty).
        """
        image = await self._safe_capture()
        if image is None:
            await self._announce("I couldn't capture an image. "
                                 "Please check the camera.")
            return []

        blocks = await self._safe_ocr(image)
        if not blocks:
            await self._announce_no_text()
            return []

        text = self._format_text_blocks(blocks)
        await self.audio_cues.chime()
        await self._announce(text)
        return blocks

    async def read_specific(self, prompt: str) -> str:
        """Use the VLM to answer a directed reading request.

        Examples of *prompt*: ``"read the menu"``, ``"what does the sign say?"``,
        ``"read the label on this bottle"``.

        Returns the VLM answer as a string (also spoken aloud).
        """
        image = await self._safe_capture()
        if image is None:
            await self._announce("I couldn't capture an image. "
                                 "Please check the camera.")
            return ""

        vlm_prompt = (
            f"A blind person is asking you to read text for them. "
            f"Their request: \"{prompt}\". "
            f"Read the relevant text in the image aloud.  If no text is "
            f"visible, say so."
        )

        answer = await self._safe_vlm_answer(image, vlm_prompt)
        if not answer:
            await self._announce_no_text()
            return ""

        await self.audio_cues.chime()
        await self._announce(answer)
        return answer

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _format_text_blocks(self, blocks: list[TextBlock]) -> str:
        """Turn a list of OCR blocks into a natural spoken narration."""
        if not blocks:
            return _NO_TEXT_MESSAGE

        # Sort top-to-bottom, left-to-right for natural reading order.
        sorted_blocks = sorted(
            blocks,
            key=lambda b: (
                b.bbox.y_min if b.bbox else 0.0,
                b.bbox.x_min if b.bbox else 0.0,
            ),
        )

        if len(sorted_blocks) == 1:
            return f"I can see text that reads: {sorted_blocks[0].text}"

        parts = ["I found several blocks of text."]
        for i, block in enumerate(sorted_blocks, 1):
            parts.append(f"Block {i}: {block.text}")
        return " ".join(parts)

    async def _announce_no_text(self) -> None:
        await self.haptics.double_pulse()
        await self._announce(_NO_TEXT_MESSAGE)

    # -- safe wrappers --------------------------------------------------

    async def _safe_capture(self) -> bytes | None:
        try:
            return await self.camera.capture_frame()
        except Exception:
            logger.exception("Camera capture failed")
            return None

    async def _safe_ocr(self, image: bytes) -> list[TextBlock]:
        try:
            return await self.ocr.read(image)
        except Exception:
            logger.exception("OCR failed")
            return []

    async def _safe_vlm_answer(self, image: bytes, prompt: str) -> str:
        try:
            return await self.vlm.answer(image, prompt)
        except Exception:
            logger.exception("VLM answer failed")
            return ""
