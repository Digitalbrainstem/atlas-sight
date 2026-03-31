"""Voice listener — wake-word detection, STT transcription, command dispatch."""
from __future__ import annotations

import abc
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from atlas_sight.config import VoiceSettings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: openai-whisper
# ---------------------------------------------------------------------------
_HAS_WHISPER = False
try:
    import whisper as _whisper  # type: ignore[import-untyped]

    _HAS_WHISPER = True
except ImportError:  # pragma: no cover
    _whisper = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Abstract STT provider
# ---------------------------------------------------------------------------

class STTProviderBase(abc.ABC):
    """Base class for speech-to-text providers."""

    @abc.abstractmethod
    async def transcribe(self, audio: bytes) -> str:
        """Transcribe raw audio bytes into text."""

    @abc.abstractmethod
    async def load_model(self) -> None:
        """Load the underlying model into memory."""

    @property
    @abc.abstractmethod
    def is_loaded(self) -> bool:
        """Return *True* when the model is ready for inference."""


# ---------------------------------------------------------------------------
# Whisper tiny STT (~75 MB)
# ---------------------------------------------------------------------------

class WhisperSTT(STTProviderBase):
    """Offline STT using OpenAI Whisper *tiny* (~75 MB RAM).

    The heavy ``whisper`` import is guarded behind ``_HAS_WHISPER`` so the rest
    of the codebase can load even when the dependency is missing.
    """

    def __init__(self, model_name: str = "tiny", language: str = "en") -> None:
        self._model_name = model_name
        self._language = language
        self._model: Any = None

    # -- STTProviderBase interface ------------------------------------------

    async def transcribe(self, audio: bytes) -> str:
        if not self.is_loaded:
            raise RuntimeError("Whisper model not loaded — call load_model() first")

        import io
        import tempfile

        import numpy as np

        # whisper expects a file path or numpy array.  We write to a short-
        # lived named tempfile so whisper can open it directly.
        buf = io.BytesIO(audio)
        try:
            # Attempt to read as WAV/raw PCM via numpy
            samples = np.frombuffer(buf.read(), dtype=np.int16).astype(np.float32) / 32768.0
        except Exception:
            # Fallback: write to disk and let whisper handle the format.
            samples = None

        if samples is not None and len(samples) > 0:
            result = await asyncio.to_thread(
                self._model.transcribe,
                samples,
                language=self._language,
                fp16=False,
            )
        else:
            # Last-resort path via tempfile (e.g. for mp3/ogg input).
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                tmp.write(audio)
                tmp.flush()
                result = await asyncio.to_thread(
                    self._model.transcribe,
                    tmp.name,
                    language=self._language,
                    fp16=False,
                )

        text: str = result.get("text", "").strip()
        logger.debug("Whisper transcribed: %r", text)
        return text

    async def load_model(self) -> None:
        if not _HAS_WHISPER:
            raise RuntimeError(
                "openai-whisper is not installed — "
                "install it with: pip install openai-whisper"
            )
        logger.info("Loading Whisper model %r …", self._model_name)
        self._model = await asyncio.to_thread(_whisper.load_model, self._model_name)
        logger.info("Whisper model %r loaded", self._model_name)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None


# ---------------------------------------------------------------------------
# Voice listener
# ---------------------------------------------------------------------------

class VoiceListener:
    """Continuous listening loop with wake-word gating and command dispatch.

    Parameters
    ----------
    stt:
        The speech-to-text provider used for transcription.
    settings:
        Voice configuration (wake words, silence timeout, etc.).
    """

    def __init__(
        self,
        stt: STTProviderBase,
        settings: VoiceSettings | None = None,
    ) -> None:
        self._stt = stt
        self._settings = settings or VoiceSettings()

        self._running: bool = False
        self._stop_event: asyncio.Event = asyncio.Event()
        self._listen_task: asyncio.Task[None] | None = None

        # Public callback — set by the caller.
        self.on_command: Callable[[str], Awaitable[None]] | None = None

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Begin the continuous listening loop in the background."""
        if self._running:
            logger.warning("VoiceListener already running")
            return

        if not self._stt.is_loaded:
            await self._stt.load_model()

        self._running = True
        self._stop_event.clear()
        self._listen_task = asyncio.create_task(self._loop(), name="voice-listener")
        logger.info("VoiceListener started")

    async def stop(self) -> None:
        """Gracefully shut down the listener."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        logger.info("VoiceListener stopped")

    # -- Public helpers ------------------------------------------------------

    async def listen_once(self) -> str | None:
        """Record a single utterance and return the transcribed text.

        Returns ``None`` when no speech is detected (silence timeout) or an
        error occurs.
        """
        audio = await self._record_audio()
        if audio is None:
            return None

        try:
            text = await self._stt.transcribe(audio)
        except Exception:
            logger.exception("Transcription failed")
            return None

        if not text:
            return None

        return text

    # -- Wake word -----------------------------------------------------------

    def _detect_wake_word(self, text: str) -> bool:
        """Return *True* if *text* starts with any configured wake word."""
        lower = text.lower().strip()
        return any(lower.startswith(w.lower()) for w in self._settings.wake_words)

    def _strip_wake_word(self, text: str) -> str:
        """Remove the leading wake word from *text*."""
        lower = text.lower().strip()
        for wake in sorted(self._settings.wake_words, key=len, reverse=True):
            prefix = wake.lower()
            if lower.startswith(prefix):
                stripped = text[len(prefix):].lstrip(" ,.")
                return stripped if stripped else text
        return text

    # -- Internal loop -------------------------------------------------------

    async def _loop(self) -> None:
        """Core listening loop — runs until :meth:`stop` is called."""
        logger.debug("Listening loop entered")

        while self._running and not self._stop_event.is_set():
            text = await self.listen_once()
            if text is None:
                continue

            if not self._detect_wake_word(text):
                logger.debug("No wake word in: %r", text)
                continue

            command_text = self._strip_wake_word(text)
            if not command_text:
                logger.debug("Wake word detected but no command followed")
                continue

            logger.info("Command detected: %r", command_text)

            if self.on_command is not None:
                try:
                    await self.on_command(command_text)
                except Exception:
                    logger.exception("on_command callback failed for: %r", command_text)

    # -- Audio capture -------------------------------------------------------

    async def _record_audio(self) -> bytes | None:
        """Capture audio from the microphone until silence is detected.

        This is a placeholder that returns ``None``.  A real implementation
        would use ``sounddevice`` or a platform-specific API to capture PCM
        frames, applying a voice-activity detector and honouring
        ``self._settings.silence_timeout_sec``.
        """
        # Wait briefly to avoid a tight busy-loop in the absence of real audio
        # hardware (unit-test / CI friendly).
        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=self._settings.silence_timeout_sec,
            )
        except asyncio.TimeoutError:
            pass

        return None
