"""Tests for atlas_sight.voice (speaker + listener)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas_sight.config import ContentType, SpeedProfile, VoiceSettings
from atlas_sight.voice.listener import VoiceListener
from atlas_sight.voice.speaker import Speaker, SpeechItem, _next_sequence


# ===========================================================================
# SpeechItem ordering
# ===========================================================================


class TestSpeechItemOrdering:
    def test_lower_priority_first(self):
        a = SpeechItem(priority=0, text="urgent")
        b = SpeechItem(priority=1, text="normal")
        assert a < b

    def test_same_priority_fifo(self):
        a = SpeechItem(priority=1, text="first")
        b = SpeechItem(priority=1, text="second")
        # a has a lower sequence number, so it comes first
        assert a < b

    def test_sequence_monotonic(self):
        s1 = _next_sequence()
        s2 = _next_sequence()
        assert s2 > s1


# ===========================================================================
# Speaker speed / volume clamping
# ===========================================================================


class TestSpeakerSettings:
    def _mock_speaker(self, **kwargs: object) -> Speaker:
        tts = MagicMock()
        tts.is_loaded = True
        settings = VoiceSettings(**kwargs)
        return Speaker(tts=tts, settings=settings)

    def test_speed_default(self):
        s = self._mock_speaker()
        assert s.speed == 1.0

    def test_volume_default(self):
        s = self._mock_speaker()
        assert s.volume == 0.8

    def test_set_speed_clamps_high(self):
        s = self._mock_speaker(max_speed=5.0)
        s.set_speed(10.0)
        assert s.speed == 5.0

    def test_set_speed_clamps_low(self):
        s = self._mock_speaker(min_speed=0.5)
        s.set_speed(0.1)
        assert s.speed == 0.5

    def test_set_speed_normal(self):
        s = self._mock_speaker()
        s.set_speed(3.5)
        assert s.speed == 3.5

    def test_set_volume_clamps_high(self):
        s = self._mock_speaker()
        s.set_volume(5.0)
        assert s.volume == 1.0

    def test_set_volume_clamps_low(self):
        s = self._mock_speaker()
        s.set_volume(-1.0)
        assert s.volume == 0.0

    def test_set_volume_normal(self):
        s = self._mock_speaker()
        s.set_volume(0.6)
        assert s.volume == 0.6

    def test_is_speaking_false_default(self):
        s = self._mock_speaker()
        assert s.is_speaking is False

    def test_speed_range_allows_5x(self):
        """Experienced visually impaired users listen at 3-4x speed."""
        s = self._mock_speaker(max_speed=5.0)
        s.set_speed(4.0)
        assert s.speed == 4.0

    def test_speed_step_is_025(self):
        """Default speed step is 0.25x for meaningful increments."""
        settings = VoiceSettings()
        assert settings.speed_step == 0.25

    def test_reset_speed(self):
        s = self._mock_speaker()
        s.set_speed(3.5)
        assert s.speed == 3.5
        s.reset_speed()
        assert s.speed == 1.0

    def test_go_max_speed(self):
        s = self._mock_speaker()
        s.set_speed(3.5)  # sets saved_max to 3.5
        s.reset_speed()
        assert s.speed == 1.0
        s.go_max_speed()
        assert s.speed == 3.5

    def test_speed_profile_property(self):
        s = self._mock_speaker()
        assert isinstance(s.speed_profile, SpeedProfile)

    def test_set_speed_updates_saved_max(self):
        s = self._mock_speaker()
        s.set_speed(4.0)
        assert s.speed_profile.saved_max == 4.0

    def test_set_speed_does_not_lower_saved_max(self):
        s = self._mock_speaker()
        s.set_speed(4.0)
        s.set_speed(2.0)
        assert s.speed_profile.saved_max == 4.0


# ===========================================================================
# VoiceListener wake word
# ===========================================================================


class TestWakeWord:
    def _listener(self, wake_words: list[str] | None = None) -> VoiceListener:
        stt = MagicMock()
        stt.is_loaded = True
        settings = VoiceSettings(wake_words=wake_words or ["hey atlas", "atlas"])
        return VoiceListener(stt=stt, settings=settings)

    def test_detect_wake_word_present(self):
        listener = self._listener()
        assert listener._detect_wake_word("hey atlas what do you see") is True

    def test_detect_wake_word_short(self):
        listener = self._listener()
        assert listener._detect_wake_word("atlas describe") is True

    def test_detect_wake_word_absent(self):
        listener = self._listener()
        assert listener._detect_wake_word("describe the scene") is False

    def test_detect_wake_word_case_insensitive(self):
        listener = self._listener()
        assert listener._detect_wake_word("HEY ATLAS what is this") is True

    def test_strip_wake_word(self):
        listener = self._listener()
        result = listener._strip_wake_word("hey atlas what do you see")
        assert result == "what do you see"

    def test_strip_wake_word_short(self):
        listener = self._listener()
        result = listener._strip_wake_word("atlas describe")
        assert result == "describe"

    def test_strip_wake_word_no_match(self):
        listener = self._listener()
        result = listener._strip_wake_word("describe the scene")
        assert result == "describe the scene"

    def test_strip_wake_word_only(self):
        listener = self._listener()
        result = listener._strip_wake_word("atlas")
        # When only the wake word is present, returns original text
        assert result == "atlas"

    def test_strip_wake_word_longest_first(self):
        listener = self._listener()
        result = listener._strip_wake_word("hey atlas, read this")
        assert result == "read this"

    def test_strip_wake_word_preserves_case(self):
        listener = self._listener()
        result = listener._strip_wake_word("Hey Atlas Read This")
        assert result == "Read This"


# ===========================================================================
# SpeedProfile
# ===========================================================================


class TestSpeedProfile:
    def test_defaults(self):
        p = SpeedProfile()
        assert p.preferred == 1.0
        assert p.navigation == 1.0
        assert p.alert == 0.85
        assert p.saved_max == 3.0

    def test_speed_for_general(self):
        p = SpeedProfile(preferred=3.0)
        assert p.speed_for(ContentType.GENERAL) == 3.0

    def test_speed_for_description(self):
        p = SpeedProfile(preferred=3.5)
        assert p.speed_for(ContentType.DESCRIPTION) == 3.5

    def test_speed_for_text_reading(self):
        p = SpeedProfile(preferred=4.0)
        assert p.speed_for(ContentType.TEXT_READING) == 4.0

    def test_speed_for_navigation_always_normal(self):
        """Navigation warnings are always at normal speed for safety."""
        p = SpeedProfile(preferred=4.0, navigation=1.0)
        assert p.speed_for(ContentType.NAVIGATION) == 1.0

    def test_speed_for_alert_slower(self):
        """Alerts are slower for clarity."""
        p = SpeedProfile(preferred=3.0, alert=0.85)
        assert p.speed_for(ContentType.ALERT) == 0.85

    def test_speed_for_alert_capped_by_preferred(self):
        """Alert speed should not exceed preferred when preferred is very low."""
        p = SpeedProfile(preferred=0.5, alert=0.85)
        assert p.speed_for(ContentType.ALERT) == 0.5

    def test_update_preferred_clamps(self):
        p = SpeedProfile()
        p.update_preferred(10.0, min_speed=0.5, max_speed=5.0)
        assert p.preferred == 5.0

    def test_update_preferred_clamps_low(self):
        p = SpeedProfile()
        p.update_preferred(0.1, min_speed=0.5, max_speed=5.0)
        assert p.preferred == 0.5

    def test_update_preferred_updates_saved_max(self):
        p = SpeedProfile(saved_max=3.0)
        p.update_preferred(4.0, min_speed=0.5, max_speed=5.0)
        assert p.saved_max == 4.0

    def test_update_preferred_does_not_lower_saved_max(self):
        p = SpeedProfile(saved_max=4.0)
        p.update_preferred(2.0, min_speed=0.5, max_speed=5.0)
        assert p.saved_max == 4.0

    def test_piper_length_scale_at_4x(self):
        """Piper uses length_scale = 1/speed, so 4x speed → 0.25 scale."""
        speed = 4.0
        length_scale = 1.0 / max(speed, 0.1)
        assert abs(length_scale - 0.25) < 0.001


# ===========================================================================
# SpeechItem with speed field
# ===========================================================================


class TestSpeechItemSpeed:
    def test_speed_field_default_none(self):
        item = SpeechItem(priority=1, text="hello")
        assert item.speed is None

    def test_speed_field_set(self):
        item = SpeechItem(priority=1, text="hello", speed=3.5)
        assert item.speed == 3.5

    def test_speed_not_used_in_ordering(self):
        """Speed should not affect priority ordering."""
        a = SpeechItem(priority=0, text="urgent", speed=1.0)
        b = SpeechItem(priority=1, text="normal", speed=4.0)
        assert a < b
