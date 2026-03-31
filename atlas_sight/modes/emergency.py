"""Emergency mode — "where am I?" and call-for-help assistance.

Activates with an unmistakable triple vibration + urgent tone.  Combines
orientation data with a detailed scene description so the user (or a
nearby person) can understand the current location.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from atlas_sight.config import Verbosity
from atlas_sight.interaction.audio_cues import AudioCues
from atlas_sight.interaction.haptics import HapticFeedback
from atlas_sight.modes.base import ModeBase
from atlas_sight.navigation.orientation import OrientationHelper
from atlas_sight.vision.camera import CameraManager
from atlas_sight.vision.vlm import VisionLMBase
from atlas_sight.voice.speaker import Speaker

logger = logging.getLogger(__name__)

_LOCATION_PROMPT = (
    "A blind person needs to know exactly where they are. "
    "Describe the scene in detail: surroundings, landmarks, street signs, "
    "building names, colours, and anything that could help identify this "
    "location to emergency services or a passer-by."
)

_SURROUNDINGS_PROMPT = (
    "Describe everything visible in this scene as if you are telling "
    "someone over the phone where this person is standing. "
    "Include street names, business signs, building features, vehicles, "
    "nearby people, and any text visible in the environment."
)


@dataclass
class EmergencyMode(ModeBase):
    """Maximum-context location awareness for emergencies."""

    camera: CameraManager = field(repr=False)
    vlm: VisionLMBase = field(repr=False)
    orientation: OrientationHelper = field(repr=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def activate(self) -> None:
        # Unmistakable multi-sensory alert so the user knows the mode changed.
        await asyncio.gather(
            self.haptics.triple_pulse(),
            self.audio_cues.danger_alert(),
        )
        await self.speaker.say_urgent("Emergency mode active. I'm here to help.")
        self._active = True
        logger.warning("Emergency mode activated")

    async def deactivate(self) -> None:
        await self._announce("Leaving emergency mode.")
        self._active = False
        logger.info("Emergency mode deactivated")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def locate(self) -> str:
        """Combine orientation and scene description for maximum context.

        Returns a spoken-aloud summary of where the user is and what is
        around them.
        """
        orientation_text, scene_text = await asyncio.gather(
            self._safe_orientation(),
            self._safe_scene_description(_LOCATION_PROMPT),
        )

        message = self._compose_location_message(orientation_text, scene_text)
        await self.audio_cues.chime()
        await self.speaker.say_urgent(message)
        return message

    async def describe_surroundings(self) -> str:
        """Provide a thorough description suitable for relaying to someone
        on the phone or nearby.

        Returns the description text (also spoken urgently).
        """
        scene_text = await self._safe_scene_description(_SURROUNDINGS_PROMPT)
        if not scene_text:
            msg = ("I'm having trouble seeing right now. "
                   "Try turning slowly so the camera can see around you.")
            await self._announce(msg, urgent=True)
            return msg

        await self.audio_cues.chime()
        await self.speaker.say_urgent(scene_text)
        return scene_text

    async def announce_emergency(self) -> str:
        """Speak the location description loudly, formatted for a nearby
        person to hear and act on.

        Returns the announcement text.
        """
        await self.speaker.stop_speaking()

        orientation_text, scene_text = await asyncio.gather(
            self._safe_orientation(),
            self._safe_scene_description(_LOCATION_PROMPT),
        )

        location = self._compose_location_message(orientation_text, scene_text)
        announcement = (
            f"Attention! A visually impaired person needs help. "
            f"{location}"
        )

        await self.audio_cues.danger_alert()
        await self.haptics.triple_pulse()
        await self.speaker.say_urgent(announcement)
        logger.warning("Emergency announcement made")
        return announcement

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compose_location_message(
        self,
        orientation_text: str,
        scene_text: str,
    ) -> str:
        """Build a single coherent location message from both data sources."""
        parts: list[str] = []

        if orientation_text:
            parts.append(f"You are facing {orientation_text}.")

        if scene_text:
            parts.append(scene_text.strip())
        else:
            parts.append("I couldn't get a clear view of the surroundings.")

        return " ".join(parts)

    # -- safe wrappers --------------------------------------------------

    async def _safe_orientation(self) -> str:
        """Return a combined heading + location description, or ``""``."""
        try:
            heading, location = await asyncio.gather(
                self.orientation.get_heading_description(),
                self.orientation.get_location_description(),
            )
            parts = [p for p in (heading, location) if p]
            return ", ".join(parts)
        except Exception:
            logger.exception("Orientation lookup failed")
            return ""

    async def _safe_scene_description(self, prompt: str) -> str:
        image = await self._safe_capture()
        if image is None:
            return ""
        try:
            return await self.vlm.describe(image, prompt)
        except Exception:
            logger.exception("VLM describe failed in emergency mode")
            return ""

    async def _safe_capture(self) -> bytes | None:
        try:
            return await self.camera.capture_frame()
        except Exception:
            logger.exception("Camera capture failed in emergency mode")
            return None
