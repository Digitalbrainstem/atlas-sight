"""Tests for atlas_sight.config — SpeedProfile, persistence, ContentType."""
from __future__ import annotations

import json

import pytest

from atlas_sight.config import (
    ContentType,
    SightConfig,
    SpeedProfile,
    Verbosity,
    VoiceSettings,
)


# ===========================================================================
# SpeedProfile
# ===========================================================================


class TestSpeedProfileConfig:
    def test_voice_settings_defaults(self):
        vs = VoiceSettings()
        assert vs.max_speed == 5.0
        assert vs.speed_step == 0.25
        assert isinstance(vs.speed_profile, SpeedProfile)

    def test_speed_profile_defaults(self):
        p = SpeedProfile()
        assert p.preferred == 1.0
        assert p.navigation == 1.0
        assert p.alert == 0.85
        assert p.saved_max == 3.0


# ===========================================================================
# Preference persistence
# ===========================================================================


class TestPreferencePersistence:
    def test_save_and_load(self, tmp_path):
        cfg = SightConfig(data_dir=tmp_path)
        cfg.voice.speed_profile.preferred = 3.5
        cfg.voice.speed_profile.saved_max = 4.0
        cfg.voice.volume = 0.6
        cfg.verbosity = Verbosity.DETAILED
        cfg.save_preferences()

        # Load into a fresh config
        cfg2 = SightConfig(data_dir=tmp_path)
        cfg2.load_preferences()
        assert cfg2.voice.speed_profile.preferred == 3.5
        assert cfg2.voice.speed_profile.saved_max == 4.0
        assert cfg2.voice.volume == 0.6
        assert cfg2.verbosity == Verbosity.DETAILED

    def test_load_missing_file(self, tmp_path):
        """Loading when no preferences file exists is a no-op."""
        cfg = SightConfig(data_dir=tmp_path)
        cfg.load_preferences()  # should not raise
        assert cfg.voice.speed_profile.preferred == 1.0

    def test_load_corrupt_file(self, tmp_path):
        """Loading a corrupt file logs a warning but doesn't crash."""
        prefs = tmp_path / "preferences.json"
        prefs.write_text("not valid json {{{", encoding="utf-8")
        cfg = SightConfig(data_dir=tmp_path)
        cfg.load_preferences()  # should not raise
        assert cfg.voice.speed_profile.preferred == 1.0

    def test_load_partial_file(self, tmp_path):
        """Loading a file with only some fields preserves defaults."""
        prefs = tmp_path / "preferences.json"
        prefs.write_text(
            json.dumps({"speed_profile": {"preferred": 2.5}}),
            encoding="utf-8",
        )
        cfg = SightConfig(data_dir=tmp_path)
        cfg.load_preferences()
        assert cfg.voice.speed_profile.preferred == 2.5
        assert cfg.voice.speed_profile.saved_max == 3.0  # kept default

    def test_save_creates_file(self, tmp_path):
        cfg = SightConfig(data_dir=tmp_path)
        cfg.save_preferences()
        assert (tmp_path / "preferences.json").exists()

    def test_speed_synced_to_profile(self, tmp_path):
        """After loading, voice.speed should match profile.preferred."""
        prefs = tmp_path / "preferences.json"
        prefs.write_text(
            json.dumps({"speed_profile": {"preferred": 3.0}}),
            encoding="utf-8",
        )
        cfg = SightConfig(data_dir=tmp_path)
        cfg.load_preferences()
        assert cfg.voice.speed == 3.0


# ===========================================================================
# ContentType enum
# ===========================================================================


class TestContentType:
    def test_all_values(self):
        expected = {"general", "description", "text_reading", "navigation", "alert"}
        actual = {ct.value for ct in ContentType}
        assert actual == expected
