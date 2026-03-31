"""Voice speaker — priority-queued TTS output with speed/volume control."""
from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from atlas_sight.config import ContentType, SpeedProfile, VoiceSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependencies for audio playback
# ---------------------------------------------------------------------------
_HAS_SOUNDDEVICE = False
try:
    import sounddevice as _sd  # type: ignore[import-untyped]

    _HAS_SOUNDDEVICE = True
except ImportError:  # pragma: no cover
    _sd = None  # type: ignore[assignment]

_HAS_SIMPLEAUDIO = False
try:
    import simpleaudio as _sa  # type: ignore[import-untyped]

    _HAS_SIMPLEAUDIO = True
except ImportError:  # pragma: no cover
    _sa = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Abstract TTS provider
# ---------------------------------------------------------------------------

class TTSProviderBase(abc.ABC):
    """Base class for text-to-speech providers."""

    @abc.abstractmethod
    async def synthesize(self, text: str, speed: float = 1.0) -> bytes:
        """Synthesize *text* into raw audio bytes (16-bit PCM, 22 050 Hz)."""

    @abc.abstractmethod
    async def load_model(self) -> None:
        """Load the underlying model into memory."""

    @property
    @abc.abstractmethod
    def is_loaded(self) -> bool:
        """Return *True* when the model is ready for inference."""


# ---------------------------------------------------------------------------
# Piper TTS (~15 MB)
# ---------------------------------------------------------------------------

_HAS_PIPER = False
try:
    import piper as _piper  # type: ignore[import-untyped]

    _HAS_PIPER = True
except ImportError:  # pragma: no cover
    _piper = None  # type: ignore[assignment]


class PiperTTS(TTSProviderBase):
    """Offline TTS using Piper (~15 MB voice model).

    The ``piper`` import is guarded behind ``_HAS_PIPER`` so the module
    remains importable even when the dependency is absent.
    """

    DEFAULT_SAMPLE_RATE = 22050

    def __init__(
        self,
        model_path: str = "",
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> None:
        self._model_path = model_path
        self._sample_rate = sample_rate
        self._voice: Any = None

    # -- TTSProviderBase interface ------------------------------------------

    async def synthesize(self, text: str, speed: float = 1.0) -> bytes:
        if not self.is_loaded:
            raise RuntimeError("Piper model not loaded — call load_model() first")

        length_scale = 1.0 / max(speed, 0.1)

        raw: bytes = await asyncio.to_thread(
            self._synthesize_sync, text, length_scale,
        )
        logger.debug("Piper synthesized %d bytes for %d chars", len(raw), len(text))
        return raw

    async def load_model(self) -> None:
        if not _HAS_PIPER:
            raise RuntimeError(
                "piper-tts is not installed — "
                "install it with: pip install piper-tts"
            )
        logger.info("Loading Piper voice model %r …", self._model_path)
        self._voice = await asyncio.to_thread(
            _piper.PiperVoice.load, self._model_path,
        )
        logger.info("Piper voice model loaded")

    @property
    def is_loaded(self) -> bool:
        return self._voice is not None

    # -- Internal -----------------------------------------------------------

    def _synthesize_sync(self, text: str, length_scale: float) -> bytes:
        """Blocking synthesis — called via ``asyncio.to_thread``."""
        import io
        import wave

        audio_chunks: list[bytes] = []
        for chunk in self._voice.synthesize_stream_raw(
            text, length_scale=length_scale,
        ):
            audio_chunks.append(chunk)

        pcm = b"".join(audio_chunks)

        # Wrap in a WAV container so downstream playback is straightforward.
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm)

        return buf.getvalue()


# ---------------------------------------------------------------------------
# Priority speech item
# ---------------------------------------------------------------------------

_sequence_counter: int = 0


def _next_sequence() -> int:
    """Monotonically increasing counter for FIFO ordering within a priority."""
    global _sequence_counter  # noqa: PLW0603
    _sequence_counter += 1
    return _sequence_counter


@dataclass(order=True)
class SpeechItem:
    """An item in the speech queue, sortable by priority then insertion order."""

    priority: int
    sequence: int = field(default_factory=_next_sequence)
    text: str = field(compare=False, default="")
    interrupt: bool = field(compare=False, default=False)
    speed: float | None = field(compare=False, default=None)


# ---------------------------------------------------------------------------
# Speaker
# ---------------------------------------------------------------------------

class Speaker:
    """Priority-based TTS output manager.

    Lower ``priority`` numbers are spoken first.  Items with
    ``interrupt=True`` flush the queue and stop any in-progress playback.

    Parameters
    ----------
    tts:
        The text-to-speech provider used for synthesis.
    settings:
        Voice configuration (speed, volume, clamp ranges).
    """

    def __init__(
        self,
        tts: TTSProviderBase,
        settings: VoiceSettings | None = None,
    ) -> None:
        self._tts = tts
        self._settings = settings or VoiceSettings()
        self._speed_profile: SpeedProfile = self._settings.speed_profile

        self._speed: float = self._speed_profile.preferred
        self._volume: float = self._settings.volume

        self._queue: asyncio.PriorityQueue[SpeechItem] = asyncio.PriorityQueue()
        self._running: bool = False
        self._speaking: bool = False
        self._processor_task: asyncio.Task[None] | None = None
        self._current_playback: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event = asyncio.Event()

    # -- Properties ----------------------------------------------------------

    @property
    def is_speaking(self) -> bool:
        """Return *True* while audio is being played."""
        return self._speaking

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def speed_profile(self) -> SpeedProfile:
        """The current speed profile with per-content-type speeds."""
        return self._speed_profile

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Start the background queue processor."""
        if self._running:
            logger.warning("Speaker already running")
            return

        if not self._tts.is_loaded:
            await self._tts.load_model()

        self._running = True
        self._stop_event.clear()
        self._processor_task = asyncio.create_task(
            self._process_queue(), name="speaker-queue",
        )
        logger.info("Speaker started (speed=%.1f, volume=%.1f)", self._speed, self._volume)

    async def stop(self) -> None:
        """Gracefully stop the speaker and drain remaining items."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        # Unblock the queue processor if it is waiting on an empty queue.
        await self._queue.put(SpeechItem(priority=999, text=""))

        if self._current_playback is not None:
            self._current_playback.cancel()
            try:
                await self._current_playback
            except asyncio.CancelledError:
                pass

        if self._processor_task is not None:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
            self._processor_task = None

        self._speaking = False
        logger.info("Speaker stopped")

    # -- Public API ----------------------------------------------------------

    async def say(
        self,
        text: str,
        priority: int = 1,
        *,
        interrupt: bool = False,
        content_type: ContentType = ContentType.GENERAL,
    ) -> None:
        """Queue *text* for synthesis and playback.

        Parameters
        ----------
        text:
            The text to speak.
        priority:
            Lower numbers are spoken first (0 = highest).
        interrupt:
            If *True*, flush the queue and stop current playback first.
        content_type:
            The kind of content being spoken.  Determines the effective
            speech speed via the :class:`SpeedProfile` — navigation
            warnings are always at normal pace; alerts are slightly
            slower; everything else uses the user's preferred speed.
        """
        if not text or not text.strip():
            return

        if interrupt:
            await self.stop_speaking()

        effective_speed = self._speed_profile.speed_for(content_type)
        item = SpeechItem(
            priority=priority,
            text=text.strip(),
            interrupt=interrupt,
            speed=effective_speed,
        )
        await self._queue.put(item)
        logger.debug(
            "Queued speech (pri=%d, spd=%.2f, type=%s): %r",
            priority, effective_speed, content_type.value, text[:60],
        )

    async def say_urgent(self, text: str) -> None:
        """Speak *text* immediately, interrupting anything in progress.

        Uses :attr:`ContentType.ALERT` speed (slightly slower than
        normal) so critical information is clear.
        """
        await self.say(text, priority=0, interrupt=True, content_type=ContentType.ALERT)

    async def stop_speaking(self) -> None:
        """Clear the queue and cancel the current playback."""
        # Drain the queue.
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

        if self._current_playback is not None:
            self._current_playback.cancel()
            try:
                await self._current_playback
            except asyncio.CancelledError:
                pass
            self._current_playback = None

        self._speaking = False
        logger.debug("Stopped speaking and cleared queue")

    # -- Speed / volume ------------------------------------------------------

    def set_speed(self, speed: float) -> None:
        """Set the preferred speech speed, clamped to [min_speed, max_speed].

        Updates both the legacy ``_speed`` attribute and the
        :class:`SpeedProfile`.
        """
        self._speed_profile.update_preferred(
            speed,
            min_speed=self._settings.min_speed,
            max_speed=self._settings.max_speed,
        )
        self._speed = self._speed_profile.preferred
        logger.info("Speech speed set to %.2f×", self._speed)

    def reset_speed(self) -> None:
        """Reset speed to 1.0× (the "normal speed" command)."""
        self.set_speed(1.0)
        logger.info("Speech speed reset to normal (1.0×)")

    def go_max_speed(self) -> None:
        """Jump to the user's saved maximum speed."""
        self.set_speed(self._speed_profile.saved_max)
        logger.info("Speech speed set to saved max (%.2f×)", self._speed)

    def set_volume(self, volume: float) -> None:
        """Set playback volume, clamped to [0.0, 1.0]."""
        self._volume = max(0.0, min(volume, 1.0))
        logger.info("Speech volume set to %.2f", self._volume)

    # -- Internal queue processor --------------------------------------------

    async def _process_queue(self) -> None:
        """Continuously pull items from the priority queue and speak them."""
        logger.debug("Speaker queue processor entered")

        while self._running and not self._stop_event.is_set():
            try:
                item: SpeechItem = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue

            if not self._running:
                self._queue.task_done()
                break

            if not item.text:
                self._queue.task_done()
                continue

            try:
                self._speaking = True
                item_speed = item.speed if item.speed is not None else self._speed
                audio = await self._tts.synthesize(item.text, speed=item_speed)
                self._current_playback = asyncio.create_task(
                    self._play_audio(audio), name="speaker-play",
                )
                await self._current_playback
            except asyncio.CancelledError:
                logger.debug("Playback cancelled for: %r", item.text[:40])
            except Exception:
                logger.exception("Speech failed for: %r", item.text[:60])
            finally:
                self._current_playback = None
                self._speaking = False
                self._queue.task_done()

    # -- Audio playback ------------------------------------------------------

    async def _play_audio(self, audio: bytes) -> None:
        """Play raw audio bytes through the system speaker.

        Tries ``sounddevice`` first, then ``simpleaudio``.  Falls back to a
        no-op if neither library is available (useful in CI / headless
        environments).
        """
        if not audio:
            return

        if _HAS_SOUNDDEVICE:
            await self._play_sounddevice(audio)
        elif _HAS_SIMPLEAUDIO:
            await self._play_simpleaudio(audio)
        else:
            logger.warning(
                "No audio backend available (install sounddevice or simpleaudio)"
            )

    async def _play_sounddevice(self, audio: bytes) -> None:
        """Play WAV bytes via *sounddevice*."""
        import io
        import wave

        import numpy as np

        buf = io.BytesIO(audio)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())

        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        # Apply volume scaling.
        samples = samples * self._volume

        if channels > 1:
            samples = samples.reshape(-1, channels)

        done = asyncio.Event()

        def _callback_finished() -> None:
            done.set()

        await asyncio.to_thread(
            _sd.play, samples, samplerate=rate,
        )
        # sounddevice.play is non-blocking; wait for completion.
        await asyncio.to_thread(_sd.wait)

    async def _play_simpleaudio(self, audio: bytes) -> None:
        """Play WAV bytes via *simpleaudio*."""
        import io
        import wave

        buf = io.BytesIO(audio)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frames = wf.readframes(wf.getnframes())

        # Volume scaling on raw PCM.
        if self._volume < 1.0:
            import numpy as np

            samples = np.frombuffer(frames, dtype=np.int16)
            samples = (samples * self._volume).astype(np.int16)
            frames = samples.tobytes()

        play_obj = _sa.play_buffer(frames, channels, sample_width, rate)
        # Wait in a thread so we don't block the event loop.
        await asyncio.to_thread(play_obj.wait_done)
