"""Audio cues (earcons) — non-speech audio feedback for blind/VI users.

Tones are synthesised from pure math (sine waves → 16-bit PCM at 22 050 Hz)
so the module works fully offline with zero external audio files.

Audio playback is guarded behind an optional ``sounddevice`` import; when the
library is unavailable the module still works — it just logs instead of
playing.
"""
from __future__ import annotations

import array
import logging
import math
from dataclasses import dataclass

from atlas_sight.config import AudioCueSettings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency — playback hardware
# ---------------------------------------------------------------------------

_HAS_SOUNDDEVICE = False
try:
    import sounddevice as sd  # type: ignore[import-untyped]

    _HAS_SOUNDDEVICE = True
except Exception:  # pragma: no cover — may be ImportError or PortAudio init error
    sd = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22_050  # Hz
BITS_PER_SAMPLE = 16
MAX_AMPLITUDE = (2 ** (BITS_PER_SAMPLE - 1)) - 1  # 32 767

# ---------------------------------------------------------------------------
# Audio cue controller
# ---------------------------------------------------------------------------


class AudioCues:
    """Synthesises and plays non-speech audio feedback.

    All tones are generated in-memory from sine waves so the module works
    offline and needs no audio asset files.

    Usage::

        cues = AudioCues(settings)
        await cues.beep()          # quick acknowledge
        await cues.warning_tone()  # obstacle approaching
    """

    def __init__(self, settings: AudioCueSettings | None = None) -> None:
        self._settings = settings or AudioCueSettings()

    # -- enabled property --------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._settings.enabled = value

    # -- high-level cues ---------------------------------------------------

    async def beep(self) -> None:
        """Short beep — command acknowledged."""
        if not self._settings.enabled:
            return
        audio = self._generate_tone(
            frequency=self._settings.beep_frequency_hz,
            duration_ms=self._settings.beep_duration_ms,
            volume=0.4,
        )
        self._play_audio(audio)

    async def chime(self) -> None:
        """Pleasant two-note chime — text detected / ready."""
        if not self._settings.enabled:
            return
        freq = self._settings.chime_frequency_hz
        note1 = self._generate_tone(freq, duration_ms=100, volume=0.35)
        note2 = self._generate_tone(int(freq * 1.25), duration_ms=150, volume=0.35)
        silence = self._generate_silence(40)
        self._play_audio(note1 + silence + note2)

    async def warning_tone(self) -> None:
        """Rising tone — obstacle approaching."""
        if not self._settings.enabled:
            return
        audio = self._generate_rising_tone(
            start_freq=self._settings.warning_frequency_hz,
            end_freq=self._settings.warning_frequency_hz + 600,
            duration_ms=400,
            volume=0.6,
        )
        self._play_audio(audio)

    async def danger_alert(self) -> None:
        """Urgent pulsing alert — immediate danger."""
        if not self._settings.enabled:
            return
        pulse = self._generate_tone(1600, duration_ms=80, volume=0.8)
        gap = self._generate_silence(40)
        audio = (pulse + gap) * 4 + pulse
        self._play_audio(audio)

    async def rising_tone(self, duration_ms: int = 500) -> None:
        """Obstacle getting closer — pitch rises."""
        if not self._settings.enabled:
            return
        audio = self._generate_rising_tone(
            start_freq=600,
            end_freq=1400,
            duration_ms=max(50, duration_ms),
            volume=0.5,
        )
        self._play_audio(audio)

    async def falling_tone(self, duration_ms: int = 500) -> None:
        """Obstacle receding — pitch falls."""
        if not self._settings.enabled:
            return
        audio = self._generate_rising_tone(
            start_freq=1400,
            end_freq=600,
            duration_ms=max(50, duration_ms),
            volume=0.5,
        )
        self._play_audio(audio)

    async def mode_switch(self) -> None:
        """Two-tone sweep indicating a mode change."""
        if not self._settings.enabled:
            return
        sweep_up = self._generate_rising_tone(500, 1000, duration_ms=120, volume=0.4)
        silence = self._generate_silence(50)
        sweep_down = self._generate_rising_tone(1000, 500, duration_ms=120, volume=0.4)
        self._play_audio(sweep_up + silence + sweep_down)

    async def error_tone(self) -> None:
        """Low descending buzz — something went wrong."""
        if not self._settings.enabled:
            return
        audio = self._generate_rising_tone(
            start_freq=500,
            end_freq=250,
            duration_ms=300,
            volume=0.55,
        )
        self._play_audio(audio)

    # -- tone generation ---------------------------------------------------

    @staticmethod
    def _generate_tone(
        frequency: int,
        duration_ms: int,
        volume: float = 0.5,
    ) -> bytes:
        """Synthesise a fixed-frequency sine wave as 16-bit PCM at 22 050 Hz.

        Parameters
        ----------
        frequency:
            Tone frequency in Hz (clamped to 20–20 000).
        duration_ms:
            Duration in milliseconds (minimum 1).
        volume:
            Amplitude multiplier in 0.0–1.0.
        """
        frequency = max(20, min(frequency, 20_000))
        duration_ms = max(1, duration_ms)
        volume = max(0.0, min(volume, 1.0))

        num_samples = int(SAMPLE_RATE * duration_ms / 1000)
        amplitude = int(MAX_AMPLITUDE * volume)
        buf = array.array("h")  # signed 16-bit

        for i in range(num_samples):
            t = i / SAMPLE_RATE
            sample = int(amplitude * math.sin(2.0 * math.pi * frequency * t))
            buf.append(max(-MAX_AMPLITUDE, min(sample, MAX_AMPLITUDE)))

        # Apply a tiny fade-in/out (2 ms each) to avoid clicks.
        _apply_fade(buf, SAMPLE_RATE, fade_ms=2)

        return buf.tobytes()

    @staticmethod
    def _generate_rising_tone(
        start_freq: int,
        end_freq: int,
        duration_ms: int,
        volume: float = 0.5,
    ) -> bytes:
        """Synthesise a linear-sweep sine tone (rising *or* falling)."""
        start_freq = max(20, min(start_freq, 20_000))
        end_freq = max(20, min(end_freq, 20_000))
        duration_ms = max(1, duration_ms)
        volume = max(0.0, min(volume, 1.0))

        num_samples = int(SAMPLE_RATE * duration_ms / 1000)
        amplitude = int(MAX_AMPLITUDE * volume)
        buf = array.array("h")

        for i in range(num_samples):
            progress = i / max(num_samples - 1, 1)
            freq = start_freq + (end_freq - start_freq) * progress
            t = i / SAMPLE_RATE
            sample = int(amplitude * math.sin(2.0 * math.pi * freq * t))
            buf.append(max(-MAX_AMPLITUDE, min(sample, MAX_AMPLITUDE)))

        _apply_fade(buf, SAMPLE_RATE, fade_ms=2)
        return buf.tobytes()

    @staticmethod
    def _generate_silence(duration_ms: int) -> bytes:
        """Return silent PCM data for the given duration."""
        num_samples = int(SAMPLE_RATE * max(1, duration_ms) / 1000)
        buf = array.array("h", [0] * num_samples)
        return buf.tobytes()

    # -- playback ----------------------------------------------------------

    @staticmethod
    def _play_audio(audio: bytes) -> None:
        """Play raw 16-bit PCM through the default audio device.

        Falls back to a log message when ``sounddevice`` is not available.
        """
        if not audio:
            return

        if not _HAS_SOUNDDEVICE:
            # Calculate duration for the log message.
            num_samples = len(audio) // 2  # 16-bit = 2 bytes per sample
            duration_ms = int(num_samples / SAMPLE_RATE * 1000)
            log.debug(
                "Audio playback stubbed (no sounddevice): %d samples, ~%d ms",
                num_samples,
                duration_ms,
            )
            return

        try:
            import numpy as np  # type: ignore[import-untyped]

            samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
            samples /= MAX_AMPLITUDE  # normalise to -1.0 … 1.0
            sd.play(samples, samplerate=SAMPLE_RATE, blocking=False)
        except Exception:
            log.warning("Audio playback failed", exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_fade(
    buf: array.array[int],
    sample_rate: int,
    fade_ms: int = 2,
) -> None:
    """Apply a short linear fade-in and fade-out to avoid audible clicks."""
    fade_samples = int(sample_rate * fade_ms / 1000)
    fade_samples = min(fade_samples, len(buf) // 2)

    for i in range(fade_samples):
        scale = i / max(fade_samples, 1)
        buf[i] = int(buf[i] * scale)
        buf[-(i + 1)] = int(buf[-(i + 1)] * scale)
