"""Identify mode — "what is this?" for a specific object.

Designed for moments when the user holds up an item or points the camera
at something and asks for identification or a follow-up question.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from atlas_sight.interaction.audio_cues import AudioCues
from atlas_sight.interaction.haptics import HapticFeedback
from atlas_sight.modes.base import ModeBase
from atlas_sight.vision.camera import CameraManager
from atlas_sight.vision.vlm import VisionLMBase
from atlas_sight.voice.speaker import Speaker

logger = logging.getLogger(__name__)

_IDENTIFY_PROMPT = (
    "A blind person is pointing their camera at something and asking "
    "\"what is this?\". Identify the main object in the center of the image. "
    "Name it, describe its color, size, brand or label if visible, and any "
    "other identifying features. Be concise and helpful."
)

_QUESTION_TEMPLATE = (
    "A blind person is looking at something through their camera and asks: "
    "\"{question}\". Answer their question based on what you see in the image. "
    "Be direct and helpful."
)


@dataclass
class IdentifyMode(ModeBase):
    """Point-and-ask identification of objects and visual content."""

    camera: CameraManager = field(repr=False)
    vlm: VisionLMBase = field(repr=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def activate(self) -> None:
        await self.haptics.pulse()
        await self._announce(
            "Identify mode. Point the camera at something and ask."
        )
        self._active = True
        logger.info("Identify mode activated")

    async def deactivate(self) -> None:
        self._active = False
        logger.info("Identify mode deactivated")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def identify(self) -> str:
        """Capture a frame and describe the main object in view.

        Returns the identification text (also spoken aloud).
        """
        image = await self._safe_capture()
        if image is None:
            msg = "I couldn't capture an image. Please check the camera."
            await self._announce(msg)
            return msg

        prompt = self._build_identify_prompt()
        result = await self._safe_vlm_describe(image, prompt)
        if not result:
            msg = "I wasn't able to identify anything. Try again."
            await self.haptics.double_pulse()
            await self._announce(msg)
            return msg

        await self.audio_cues.chime()
        await self._announce(result)
        return result

    async def answer_question(self, question: str) -> str:
        """Answer a specific question about what the camera currently sees.

        Returns the answer text (also spoken aloud).
        """
        if not question or not question.strip():
            msg = "I didn't catch a question. Could you try again?"
            await self._announce(msg)
            return msg

        image = await self._safe_capture()
        if image is None:
            msg = "I couldn't capture an image. Please check the camera."
            await self._announce(msg)
            return msg

        prompt = self._build_question_prompt(question)
        answer = await self._safe_vlm_answer(image, prompt)
        if not answer:
            msg = "I wasn't able to answer that. Try asking differently."
            await self.haptics.double_pulse()
            await self._announce(msg)
            return msg

        await self.audio_cues.chime()
        await self._announce(answer)
        return answer

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_identify_prompt(self) -> str:
        return _IDENTIFY_PROMPT

    def _build_question_prompt(self, question: str) -> str:
        return _QUESTION_TEMPLATE.format(question=question)

    # -- safe wrappers --------------------------------------------------

    async def _safe_capture(self) -> bytes | None:
        try:
            return await self.camera.capture_frame()
        except Exception:
            logger.exception("Camera capture failed")
            return None

    async def _safe_vlm_describe(self, image: bytes, prompt: str) -> str:
        try:
            return await self.vlm.describe(image, prompt)
        except Exception:
            logger.exception("VLM describe failed")
            return ""

    async def _safe_vlm_answer(self, image: bytes, prompt: str) -> str:
        try:
            return await self.vlm.answer(image, prompt)
        except Exception:
            logger.exception("VLM answer failed")
            return ""
