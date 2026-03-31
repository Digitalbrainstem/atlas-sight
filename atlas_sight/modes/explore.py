"""Explore mode — continuous scene narration (the default mode).

Captures frames at a configurable interval, runs them through the VLM and
object detector, warns about obstacles, and narrates the result to the user.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from atlas_sight.config import Verbosity
from atlas_sight.data.models import DetectedObject, Obstacle, Scene, Severity
from atlas_sight.interaction.audio_cues import AudioCues
from atlas_sight.interaction.haptics import HapticFeedback
from atlas_sight.modes.base import ModeBase
from atlas_sight.navigation.obstacle import ObstacleWarner
from atlas_sight.vision.camera import CameraManager
from atlas_sight.vision.detector import ObjectDetectorBase
from atlas_sight.vision.vlm import VisionLMBase
from atlas_sight.voice.speaker import Speaker

logger = logging.getLogger(__name__)

_PROMPTS: dict[Verbosity, str] = {
    Verbosity.BRIEF: (
        "Describe this scene in one sentence for a blind person."
    ),
    Verbosity.NORMAL: (
        "Describe this scene for a blind person. "
        "Mention people, obstacles, text, and spatial layout. Be concise."
    ),
    Verbosity.DETAILED: (
        "Describe this scene in detail for a blind person. "
        "Include colors, distances, spatial relationships, text, "
        "and any potential hazards."
    ),
}


@dataclass
class ExploreMode(ModeBase):
    """Continuous scene narration for general environmental awareness."""

    camera: CameraManager = field(repr=False)
    vlm: VisionLMBase = field(repr=False)
    detector: ObjectDetectorBase = field(repr=False)
    obstacle_warner: ObstacleWarner = field(repr=False)

    _continuous_task: asyncio.Task[None] | None = field(
        default=None, init=False, repr=False,
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def activate(self) -> None:
        await self.haptics.pulse()
        await self._announce("Explore mode active.")
        self._active = True
        logger.info("Explore mode activated")

    async def deactivate(self) -> None:
        await self.stop_continuous()
        self._active = False
        logger.info("Explore mode deactivated")

    # ------------------------------------------------------------------
    # Single-shot scene description
    # ------------------------------------------------------------------

    async def describe_scene(
        self,
        verbosity: Verbosity = Verbosity.NORMAL,
    ) -> Scene:
        """Capture a frame, analyse it, speak the description, and return a
        :class:`Scene` snapshot."""
        image = await self._safe_capture()
        if image is None:
            await self._announce("I couldn't capture an image. "
                                 "Please check the camera.")
            return Scene(description="Camera unavailable.")

        # Run VLM description and object detection concurrently.
        prompt = self._build_prompt(verbosity)
        vlm_text, objects = await asyncio.gather(
            self._safe_vlm_describe(image, prompt),
            self._safe_detect(image),
        )

        obstacles = await self._safe_analyze_obstacles(objects)
        description = self._compose_description(vlm_text, objects, obstacles)

        await self.audio_cues.chime()
        await self._announce(description)

        return Scene(
            description=description,
            objects=objects,
            obstacles=obstacles,
            timestamp=time.time(),
            detail_level=verbosity.value,
            raw_image=image,
        )

    # ------------------------------------------------------------------
    # Continuous narration loop
    # ------------------------------------------------------------------

    async def start_continuous(self, interval_sec: float = 3.0) -> None:
        """Begin continuous scene narration every *interval_sec* seconds."""
        await self.stop_continuous()
        self._continuous_task = asyncio.create_task(
            self._continuous_loop(max(0.5, interval_sec)),
        )
        logger.info("Continuous narration started (%.1fs interval)", interval_sec)

    async def stop_continuous(self) -> None:
        """Cancel the continuous narration loop if running."""
        if self._continuous_task is not None and not self._continuous_task.done():
            self._continuous_task.cancel()
            try:
                await self._continuous_task
            except asyncio.CancelledError:
                pass
            self._continuous_task = None
            logger.info("Continuous narration stopped")

    @property
    def is_continuous(self) -> bool:
        """Whether the continuous narration loop is currently running."""
        return (
            self._continuous_task is not None
            and not self._continuous_task.done()
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(self, verbosity: Verbosity) -> str:
        return _PROMPTS.get(verbosity, _PROMPTS[Verbosity.NORMAL])

    def _compose_description(
        self,
        vlm_text: str,
        objects: list[DetectedObject],
        obstacles: list[Obstacle],
    ) -> str:
        """Merge VLM prose with obstacle alerts into a single narration."""
        parts: list[str] = []

        if vlm_text:
            parts.append(vlm_text.strip())

        # Append obstacle warnings — urgent ones first.
        danger = [o for o in obstacles if o.severity == Severity.DANGER]
        warnings = [o for o in obstacles if o.severity == Severity.WARNING]

        for obs in danger:
            parts.append(
                f"Warning: {obs.label} directly ahead, "
                f"about {obs.distance_m:.1f} metres {obs.direction}."
            )
        for obs in warnings:
            parts.append(
                f"Caution: {obs.label} "
                f"about {obs.distance_m:.1f} metres to the {obs.direction}."
            )

        return " ".join(parts) if parts else "I can't make out the scene."

    # -- async helpers with error boundaries ----------------------------

    async def _continuous_loop(self, interval: float) -> None:
        """Background loop — runs until cancelled."""
        try:
            while True:
                await self.describe_scene()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Continuous narration loop crashed")
            await self._announce("Scene narration interrupted.")

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

    async def _safe_detect(self, image: bytes) -> list[DetectedObject]:
        try:
            return await self.detector.detect(image)
        except Exception:
            logger.exception("Object detection failed")
            return []

    async def _safe_analyze_obstacles(
        self,
        objects: list[DetectedObject],
    ) -> list[Obstacle]:
        try:
            return await self.obstacle_warner.analyze(objects)
        except Exception:
            logger.exception("Obstacle analysis failed")
            return []
