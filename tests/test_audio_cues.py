"""Tests for atlas_sight.interaction.audio_cues.AudioCues."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from atlas_sight.config import AudioCueSettings
from atlas_sight.interaction.audio_cues import AudioCues, SAMPLE_RATE


@pytest.fixture()
def cues() -> AudioCues:
    return AudioCues()


@pytest.fixture()
def disabled_cues() -> AudioCues:
    return AudioCues(AudioCueSettings(enabled=False))


# ---------------------------------------------------------------------------
# Tone generation
# ---------------------------------------------------------------------------


class TestToneGeneration:
    def test_generate_tone_returns_bytes(self):
        audio = AudioCues._generate_tone(440, duration_ms=100, volume=0.5)
        assert isinstance(audio, bytes)
        assert len(audio) > 0

    def test_generate_tone_length(self):
        duration_ms = 100
        audio = AudioCues._generate_tone(440, duration_ms=duration_ms, volume=0.5)
        expected_samples = int(SAMPLE_RATE * duration_ms / 1000)
        # 2 bytes per sample (16-bit)
        assert len(audio) == expected_samples * 2

    def test_generate_tone_clamps_frequency(self):
        low = AudioCues._generate_tone(1, duration_ms=10, volume=0.5)
        assert isinstance(low, bytes)
        assert len(low) > 0

    def test_generate_rising_tone(self):
        audio = AudioCues._generate_rising_tone(400, 800, duration_ms=100, volume=0.5)
        assert isinstance(audio, bytes)
        assert len(audio) > 0

    def test_generate_silence(self):
        audio = AudioCues._generate_silence(50)
        assert isinstance(audio, bytes)
        expected_samples = int(SAMPLE_RATE * 50 / 1000)
        assert len(audio) == expected_samples * 2
        # All zeros
        assert all(b == 0 for b in audio)


# ---------------------------------------------------------------------------
# Enabled / disabled toggle
# ---------------------------------------------------------------------------


class TestEnabledToggle:
    def test_enabled_default(self, cues: AudioCues):
        assert cues.enabled is True

    def test_disabled(self, disabled_cues: AudioCues):
        assert disabled_cues.enabled is False

    def test_toggle(self, cues: AudioCues):
        cues.enabled = False
        assert cues.enabled is False
        cues.enabled = True
        assert cues.enabled is True

    async def test_beep_skipped_when_disabled(self, disabled_cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await disabled_cues.beep()
            mock_play.assert_not_called()

    async def test_warning_tone_skipped_when_disabled(self, disabled_cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await disabled_cues.warning_tone()
            mock_play.assert_not_called()


# ---------------------------------------------------------------------------
# All cue methods callable
# ---------------------------------------------------------------------------


class TestCueMethods:
    async def test_beep(self, cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await cues.beep()
            mock_play.assert_called_once()

    async def test_chime(self, cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await cues.chime()
            mock_play.assert_called_once()

    async def test_warning_tone(self, cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await cues.warning_tone()
            mock_play.assert_called_once()

    async def test_danger_alert(self, cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await cues.danger_alert()
            mock_play.assert_called_once()

    async def test_rising_tone(self, cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await cues.rising_tone(200)
            mock_play.assert_called_once()

    async def test_falling_tone(self, cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await cues.falling_tone(200)
            mock_play.assert_called_once()

    async def test_mode_switch(self, cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await cues.mode_switch()
            mock_play.assert_called_once()

    async def test_error_tone(self, cues: AudioCues):
        with patch.object(AudioCues, "_play_audio") as mock_play:
            await cues.error_tone()
            mock_play.assert_called_once()
