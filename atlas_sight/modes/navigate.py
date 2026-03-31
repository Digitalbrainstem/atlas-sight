"""Navigate mode — guided walking assistance with obstacle detection.

Continuously scans for obstacles, warns with escalating urgency, and
provides compass / landmark orientation so the user can walk safely.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from atlas_sight.data.models import DetectedObject, Obstacle, Scene, Severity
from atlas_sight.interaction.audio_cues import AudioCues
from atlas_sight.interaction.haptics import HapticFeedback
from atlas_sight.modes.base import ModeBase
from atlas_sight.navigation.obstacle import ObstacleWarner
from atlas_sight.navigation.orientation import OrientationHelper
from atlas_sight.vision.camera import CameraManager
from atlas_sight.vision.detector import ObjectDetectorBase
from atlas_sight.voice.speaker import Speaker

logger = logging.getLogger(__name__)


@dataclass
class NavigateMode(ModeBase):
    """Guided walking with continuous obstacle scanning."""

    camera: CameraManager = field(repr=False)
    detector: ObjectDetectorBase = field(repr=False)
    orientation: OrientationHelper = field(repr=False)
    obstacle_warner: ObstacleWarner = field(repr=False)

    _scan_task: asyncio.Task[None] | None = field(
        default=None, init=False, repr=False,
    )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def activate(self) -> None:
        await self.haptics.double_pulse()
        heading = await self._safe_heading()
        greeting = "Navigate mode active."
        if heading:
            greeting += f" You are facing {heading}."
        await self._announce(greeting)
        self._active = True
        logger.info("Navigate mode activated")

    async def deactivate(self) -> None:
        await self.stop_scanning()
        self._active = False
        logger.info("Navigate mode deactivated")

    # ------------------------------------------------------------------
    # Single-shot obstacle scan
    # ------------------------------------------------------------------

    async def scan_ahead(self) -> list[Obstacle]:
        """Capture a frame, detect objects, and return analysed obstacles."""
        image = await self._safe_capture()
        if image is None:
            return []

        objects = await self._safe_detect(image)
        obstacles = await self._safe_analyze(objects)

        if obstacles:
            warning = self._prioritize_warnings(obstacles)
            has_danger = any(o.severity == Severity.DANGER for o in obstacles)
            if has_danger:
                await self.audio_cues.danger_alert()
                await self.haptics.triple_pulse()
                await self._announce_interrupt(warning)
            else:
                await self.audio_cues.warning_tone()
                await self.haptics.pulse()
                await self._announce(warning)

        return obstacles

    # ------------------------------------------------------------------
    # Continuous scanning loop
    # ------------------------------------------------------------------

    async def start_scanning(self, interval_sec: float = 1.0) -> None:
        """Begin continuous obstacle scanning every *interval_sec* seconds."""
        await self.stop_scanning()
        self._scan_task = asyncio.create_task(
            self._scan_loop(max(0.2, interval_sec)),
        )
        logger.info("Obstacle scanning started (%.1fs interval)", interval_sec)

    async def stop_scanning(self) -> None:
        """Cancel the continuous scanning loop if running."""
        if self._scan_task is not None and not self._scan_task.done():
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None
            logger.info("Obstacle scanning stopped")

    @property
    def is_scanning(self) -> bool:
        """Whether the background obstacle scanner is running."""
        return self._scan_task is not None and not self._scan_task.done()

    # ------------------------------------------------------------------
    # Orientation helpers
    # ------------------------------------------------------------------

    async def report_heading(self) -> None:
        """Speak the current compass heading."""
        heading = await self._safe_heading()
        if heading:
            await self._announce(f"You are facing {heading}.")
        else:
            await self._announce("Compass heading is not available.")

    async def save_current_location(self, name: str) -> None:
        """Save the current position as a named landmark."""
        try:
            await self.orientation.save_landmark(name)
            await self.audio_cues.chime()
            await self._announce(f"Location saved as {name}.")
            logger.info("Landmark saved: %s", name)
        except Exception:
            logger.exception("Failed to save landmark '%s'", name)
            await self._announce("Sorry, I couldn't save the location.")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prioritize_warnings(self, obstacles: list[Obstacle]) -> str:
        """Build a spoken warning string, most urgent obstacles first."""
        if not obstacles:
            return ""

        ordered = sorted(
            obstacles,
            key=lambda o: (
                0 if o.severity == Severity.DANGER else
                1 if o.severity == Severity.WARNING else 2,
                o.distance_m,
            ),
        )

        parts: list[str] = []
        for obs in ordered:
            if obs.severity == Severity.DANGER:
                parts.append(
                    f"Stop! {obs.label} {obs.distance_m:.1f} metres "
                    f"{obs.direction}."
                )
            elif obs.severity == Severity.WARNING:
                parts.append(
                    f"Caution, {obs.label} {obs.distance_m:.1f} metres "
                    f"{obs.direction}."
                )
            else:
                parts.append(
                    f"{obs.label} nearby to the {obs.direction}."
                )

        return " ".join(parts)

    async def _scan_loop(self, interval: float) -> None:
        """Background loop — runs until cancelled."""
        try:
            while True:
                await self.scan_ahead()
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Obstacle scan loop crashed")
            await self._announce("Navigation scanning interrupted.")

    # -- safe wrappers --------------------------------------------------

    async def _safe_capture(self) -> bytes | None:
        try:
            return await self.camera.capture_frame()
        except Exception:
            logger.exception("Camera capture failed")
            return None

    async def _safe_detect(self, image: bytes) -> list[DetectedObject]:
        try:
            return await self.detector.detect(image)
        except Exception:
            logger.exception("Object detection failed")
            return []

    async def _safe_analyze(
        self,
        objects: list[DetectedObject],
    ) -> list[Obstacle]:
        try:
            return await self.obstacle_warner.analyze(objects)
        except Exception:
            logger.exception("Obstacle analysis failed")
            return []

    async def _safe_heading(self) -> str:
        try:
            return await self.orientation.get_heading_description()
        except Exception:
            logger.exception("Heading lookup failed")
            return ""
