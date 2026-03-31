"""Tests for atlas_sight.interaction.haptics.HapticFeedback."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from atlas_sight.config import HapticPattern
from atlas_sight.interaction.haptics import (
    HapticFeedback,
    PREDEFINED_PATTERNS,
)


@pytest.fixture()
def haptics() -> HapticFeedback:
    return HapticFeedback(enabled=True)


@pytest.fixture()
def disabled_haptics() -> HapticFeedback:
    return HapticFeedback(enabled=False)


# ---------------------------------------------------------------------------
# Basic pulses
# ---------------------------------------------------------------------------


class TestPulse:
    async def test_pulse(self, haptics: HapticFeedback):
        with patch.object(haptics, "_vibrate", new_callable=AsyncMock) as mock:
            await haptics.pulse(100)
            mock.assert_awaited_once_with(100)

    async def test_pulse_clamps_min(self, haptics: HapticFeedback):
        with patch.object(haptics, "_vibrate", new_callable=AsyncMock) as mock:
            await haptics.pulse(-10)
            mock.assert_awaited_once_with(1)

    async def test_double_pulse(self, haptics: HapticFeedback):
        with patch.object(haptics, "_vibrate", new_callable=AsyncMock) as mock:
            await haptics.double_pulse()
            assert mock.await_count == 2

    async def test_triple_pulse(self, haptics: HapticFeedback):
        with patch.object(haptics, "_vibrate", new_callable=AsyncMock) as mock:
            await haptics.triple_pulse()
            assert mock.await_count == 3


# ---------------------------------------------------------------------------
# Enabled / disabled
# ---------------------------------------------------------------------------


class TestEnabledToggle:
    async def test_disabled_skips_pulse(self, disabled_haptics: HapticFeedback):
        with patch.object(disabled_haptics, "_vibrate", new_callable=AsyncMock) as mock:
            await disabled_haptics.pulse()
            mock.assert_not_awaited()

    async def test_disabled_skips_double_pulse(self, disabled_haptics: HapticFeedback):
        with patch.object(disabled_haptics, "_vibrate", new_callable=AsyncMock) as mock:
            await disabled_haptics.double_pulse()
            mock.assert_not_awaited()

    async def test_disabled_skips_triple_pulse(self, disabled_haptics: HapticFeedback):
        with patch.object(disabled_haptics, "_vibrate", new_callable=AsyncMock) as mock:
            await disabled_haptics.triple_pulse()
            mock.assert_not_awaited()

    def test_enabled_property_getter(self, haptics: HapticFeedback):
        assert haptics.enabled is True

    def test_enabled_property_setter(self, haptics: HapticFeedback):
        haptics.enabled = False
        assert haptics.enabled is False

    async def test_disable_skips_play_pattern(self, disabled_haptics: HapticFeedback):
        with patch.object(disabled_haptics, "_vibrate", new_callable=AsyncMock) as mock:
            pattern = HapticPattern(name="test", pulses=[(100, 50)])
            await disabled_haptics.play_pattern(pattern)
            mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# Predefined patterns
# ---------------------------------------------------------------------------


class TestPredefinedPatterns:
    def test_acknowledge_exists(self):
        assert "acknowledge" in PREDEFINED_PATTERNS

    def test_warning_exists(self):
        p = PREDEFINED_PATTERNS["warning"]
        assert len(p.pulses) == 3

    def test_danger_exists(self):
        p = PREDEFINED_PATTERNS["danger"]
        assert len(p.pulses) == 6

    def test_heartbeat_exists(self):
        assert "heartbeat" in PREDEFINED_PATTERNS

    def test_success_exists(self):
        assert "success" in PREDEFINED_PATTERNS

    def test_navigate_exists(self):
        assert "navigate" in PREDEFINED_PATTERNS

    async def test_play_pattern(self, haptics: HapticFeedback):
        with patch.object(haptics, "_vibrate", new_callable=AsyncMock) as mock:
            pattern = HapticPattern(name="test", pulses=[(100, 50), (200, 0)])
            await haptics.play_pattern(pattern)
            assert mock.await_count == 2


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------


class TestStop:
    async def test_stop(self, haptics: HapticFeedback):
        await haptics.stop()
        assert haptics._stopped is True
