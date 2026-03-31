"""Abstract base class for all Atlas Sight interaction modes."""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field

from atlas_sight.interaction.audio_cues import AudioCues
from atlas_sight.interaction.haptics import HapticFeedback
from atlas_sight.voice.speaker import Speaker

logger = logging.getLogger(__name__)


@dataclass
class ModeBase(abc.ABC):
    """Base class every interaction mode must extend.

    Provides lifecycle hooks (activate / deactivate) and shared references to
    the speaker and feedback peripherals that every mode needs.
    """

    speaker: Speaker
    haptics: HapticFeedback
    audio_cues: AudioCues
    _active: bool = field(default=False, init=False, repr=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def activate(self) -> None:
        """Enter this mode — announce it and initialise any background work."""

    @abc.abstractmethod
    async def deactivate(self) -> None:
        """Leave this mode — stop background work and clean up."""

    @property
    def is_active(self) -> bool:
        """Whether the mode is currently the active interaction mode."""
        return self._active

    # ------------------------------------------------------------------
    # Helpers available to every mode
    # ------------------------------------------------------------------

    async def _announce(self, text: str, *, urgent: bool = False) -> None:
        """Speak *text* to the user, choosing urgency level."""
        try:
            if urgent:
                await self.speaker.say_urgent(text)
            else:
                await self.speaker.say(text, priority=1, interrupt=False)
        except Exception:
            logger.exception("Failed to speak announcement")

    async def _announce_interrupt(self, text: str) -> None:
        """Interrupt current speech and speak *text* immediately."""
        try:
            await self.speaker.say(text, priority=0, interrupt=True)
        except Exception:
            logger.exception("Failed to speak interrupt announcement")
