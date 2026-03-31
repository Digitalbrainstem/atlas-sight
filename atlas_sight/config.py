"""Atlas Sight configuration — all settings for the accessibility assistant."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class Verbosity(Enum):
    """How much detail to include in scene descriptions."""
    BRIEF = "brief"
    NORMAL = "normal"
    DETAILED = "detailed"


class Mode(Enum):
    """Interaction modes."""
    EXPLORE = "explore"
    READ = "read"
    NAVIGATE = "navigate"
    IDENTIFY = "identify"
    EMERGENCY = "emergency"


class ContentType(Enum):
    """Content types that determine speech speed.

    Different kinds of spoken output need different speeds:
    navigation warnings are always at normal pace (safety critical),
    while scene descriptions honour the user's preferred speed.
    """
    GENERAL = "general"
    DESCRIPTION = "description"
    TEXT_READING = "text_reading"
    NAVIGATION = "navigation"
    ALERT = "alert"


@dataclass
class SpeedProfile:
    """Per-content-type speech speed preferences.

    Experienced visually impaired users listen at 3–4× normal speed.
    Safety-critical output (navigation warnings) is always spoken at
    normal pace, and alerts are slightly slower for clarity.

    ``preferred`` is the user's chosen base speed for everyday content.
    ``saved_max`` remembers the fastest speed the user has explicitly
    set — accessible via the "max speed" voice command.
    """
    preferred: float = 1.0
    navigation: float = 1.0
    alert: float = 0.85
    saved_max: float = 3.0

    def speed_for(self, content_type: ContentType) -> float:
        """Return the effective speech speed for *content_type*."""
        if content_type is ContentType.NAVIGATION:
            return self.navigation
        if content_type is ContentType.ALERT:
            return min(self.alert, self.preferred)
        # GENERAL, DESCRIPTION, TEXT_READING all use preferred speed
        return self.preferred

    def update_preferred(self, speed: float, *, min_speed: float, max_speed: float) -> None:
        """Set the preferred speed, clamped to the allowed range.

        Also updates ``saved_max`` if the new speed exceeds it.
        """
        self.preferred = max(min_speed, min(speed, max_speed))
        if self.preferred > self.saved_max:
            self.saved_max = self.preferred


@dataclass
class VoiceSettings:
    """TTS/STT configuration."""
    speed: float = 1.0
    volume: float = 0.8
    min_speed: float = 0.5
    max_speed: float = 5.0
    speed_step: float = 0.25
    volume_step: float = 0.1
    wake_words: list[str] = field(default_factory=lambda: ["hey atlas", "atlas"])
    silence_timeout_sec: float = 2.0
    speed_profile: SpeedProfile = field(default_factory=SpeedProfile)


@dataclass
class VisionSettings:
    """Camera and vision model configuration."""
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    capture_interval_sec: float = 0.5
    vlm_model_path: str = ""
    ocr_confidence_threshold: float = 0.5
    detection_confidence_threshold: float = 0.4
    max_image_size: int = 448


@dataclass
class NavigationSettings:
    """Navigation and obstacle detection configuration."""
    obstacle_warn_distance_m: float = 2.0
    obstacle_danger_distance_m: float = 0.8
    scan_interval_sec: float = 0.3


@dataclass
class HapticPattern:
    """A vibration pattern as a sequence of (on_ms, off_ms) pairs."""
    name: str
    pulses: list[tuple[int, int]]


@dataclass
class AudioCueSettings:
    """Audio feedback configuration."""
    enabled: bool = True
    haptics_enabled: bool = True
    beep_frequency_hz: int = 800
    beep_duration_ms: int = 100
    warning_frequency_hz: int = 1200
    chime_frequency_hz: int = 1000


@dataclass
class HistorySettings:
    """Session history configuration."""
    max_entries: int = 100
    max_bookmarks: int = 50
    dedup_similarity_threshold: float = 0.8


@dataclass
class SightConfig:
    """Top-level configuration for Atlas Sight."""
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    vision: VisionSettings = field(default_factory=VisionSettings)
    navigation: NavigationSettings = field(default_factory=NavigationSettings)
    audio_cues: AudioCueSettings = field(default_factory=AudioCueSettings)
    history: HistorySettings = field(default_factory=HistorySettings)
    verbosity: Verbosity = Verbosity.NORMAL
    initial_mode: Mode = Mode.EXPLORE
    data_dir: Path = field(default_factory=lambda: Path.home() / ".atlas-sight")

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Preference persistence
    # ------------------------------------------------------------------

    @property
    def _preferences_path(self) -> Path:
        return self.data_dir / "preferences.json"

    def save_preferences(self) -> None:
        """Persist user preferences (speed profile, volume) to disk."""
        data = {
            "speed_profile": asdict(self.voice.speed_profile),
            "volume": self.voice.volume,
            "verbosity": self.verbosity.value,
        }
        try:
            self._preferences_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8",
            )
            logger.debug("Preferences saved to %s", self._preferences_path)
        except OSError:
            logger.warning("Could not save preferences", exc_info=True)

    def load_preferences(self) -> None:
        """Load saved preferences from disk, if they exist."""
        path = self._preferences_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "speed_profile" in data:
                sp = data["speed_profile"]
                profile = self.voice.speed_profile
                profile.preferred = float(sp.get("preferred", profile.preferred))
                profile.navigation = float(sp.get("navigation", profile.navigation))
                profile.alert = float(sp.get("alert", profile.alert))
                profile.saved_max = float(sp.get("saved_max", profile.saved_max))
                self.voice.speed = profile.preferred
            if "volume" in data:
                self.voice.volume = float(data["volume"])
            if "verbosity" in data:
                self.verbosity = Verbosity(data["verbosity"])
            logger.info("Preferences loaded from %s", path)
        except (OSError, json.JSONDecodeError, ValueError, KeyError):
            logger.warning("Could not load preferences", exc_info=True)
