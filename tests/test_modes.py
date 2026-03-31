"""Tests for atlas_sight.modes (explore, read, navigate, identify, emergency)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from atlas_sight.data.models import Obstacle, Severity, TextBlock
from atlas_sight.interaction.audio_cues import AudioCues
from atlas_sight.interaction.haptics import HapticFeedback
from atlas_sight.modes.emergency import EmergencyMode
from atlas_sight.modes.explore import ExploreMode
from atlas_sight.modes.identify import IdentifyMode
from atlas_sight.modes.navigate import NavigateMode
from atlas_sight.modes.read import ReadMode
from atlas_sight.vision.camera import CameraManager
from atlas_sight.voice.speaker import Speaker


def _mock_speaker() -> Speaker:
    s = MagicMock(spec=Speaker)
    s.say = AsyncMock()
    s.say_urgent = AsyncMock()
    s.stop_speaking = AsyncMock()
    return s


def _mock_haptics() -> HapticFeedback:
    h = MagicMock(spec=HapticFeedback)
    h.pulse = AsyncMock()
    h.double_pulse = AsyncMock()
    h.triple_pulse = AsyncMock()
    return h


def _mock_audio_cues() -> AudioCues:
    a = MagicMock(spec=AudioCues)
    a.chime = AsyncMock()
    a.warning_tone = AsyncMock()
    a.danger_alert = AsyncMock()
    a.mode_switch = AsyncMock()
    a.beep = AsyncMock()
    return a


def _mock_camera(frame: bytes | None = b"\x00\x01\x02") -> CameraManager:
    c = MagicMock(spec=CameraManager)
    c.capture_frame = AsyncMock(return_value=frame)
    return c


# ===========================================================================
# ExploreMode
# ===========================================================================


class TestExploreMode:
    def _make(self) -> ExploreMode:
        vlm = MagicMock()
        vlm.describe = AsyncMock(return_value="A park with trees and people.")
        detector = MagicMock()
        detector.detect = AsyncMock(return_value=[])
        obstacle_warner = MagicMock()
        obstacle_warner.analyze = AsyncMock(return_value=[])
        return ExploreMode(
            speaker=_mock_speaker(),
            haptics=_mock_haptics(),
            audio_cues=_mock_audio_cues(),
            camera=_mock_camera(),
            vlm=vlm,
            detector=detector,
            obstacle_warner=obstacle_warner,
        )

    async def test_activate(self):
        mode = self._make()
        await mode.activate()
        assert mode.is_active is True
        mode.haptics.pulse.assert_awaited_once()

    async def test_deactivate(self):
        mode = self._make()
        await mode.activate()
        await mode.deactivate()
        assert mode.is_active is False

    async def test_describe_scene(self):
        mode = self._make()
        scene = await mode.describe_scene()
        assert scene.description != ""
        mode.audio_cues.chime.assert_awaited_once()

    async def test_describe_scene_no_camera(self):
        mode = self._make()
        mode.camera.capture_frame = AsyncMock(return_value=None)
        scene = await mode.describe_scene()
        assert "unavailable" in scene.description.lower()


# ===========================================================================
# ReadMode
# ===========================================================================


class TestReadMode:
    def _make(self, blocks: list[TextBlock] | None = None) -> ReadMode:
        vlm = MagicMock()
        vlm.answer = AsyncMock(return_value="the sign says exit")
        ocr = MagicMock()
        ocr.read = AsyncMock(return_value=blocks or [])
        return ReadMode(
            speaker=_mock_speaker(),
            haptics=_mock_haptics(),
            audio_cues=_mock_audio_cues(),
            camera=_mock_camera(),
            vlm=vlm,
            ocr=ocr,
        )

    async def test_activate(self):
        mode = self._make()
        await mode.activate()
        assert mode.is_active is True

    async def test_deactivate(self):
        mode = self._make()
        await mode.activate()
        await mode.deactivate()
        assert mode.is_active is False

    async def test_read_text_no_text(self):
        mode = self._make(blocks=[])
        result = await mode.read_text()
        assert result == []
        mode.haptics.double_pulse.assert_awaited()

    async def test_read_text_with_blocks(self):
        blocks = [
            TextBlock(text="Exit", confidence=0.9),
            TextBlock(text="Room 101", confidence=0.8),
        ]
        mode = self._make(blocks=blocks)
        result = await mode.read_text()
        assert len(result) == 2
        mode.audio_cues.chime.assert_awaited()

    async def test_read_text_no_camera(self):
        mode = self._make()
        mode.camera.capture_frame = AsyncMock(return_value=None)
        result = await mode.read_text()
        assert result == []


# ===========================================================================
# NavigateMode
# ===========================================================================


class TestNavigateMode:
    def _make(self, obstacles: list[Obstacle] | None = None) -> NavigateMode:
        detector = MagicMock()
        detector.detect = AsyncMock(return_value=[])
        orientation = MagicMock()
        orientation.get_heading_description = AsyncMock(return_value="You are facing north")
        obstacle_warner = MagicMock()
        obstacle_warner.analyze = AsyncMock(return_value=obstacles or [])
        return NavigateMode(
            speaker=_mock_speaker(),
            haptics=_mock_haptics(),
            audio_cues=_mock_audio_cues(),
            camera=_mock_camera(),
            detector=detector,
            orientation=orientation,
            obstacle_warner=obstacle_warner,
        )

    async def test_activate(self):
        mode = self._make()
        await mode.activate()
        assert mode.is_active is True
        mode.haptics.double_pulse.assert_awaited()

    async def test_deactivate(self):
        mode = self._make()
        await mode.activate()
        await mode.deactivate()
        assert mode.is_active is False

    async def test_scan_ahead_clear(self):
        mode = self._make(obstacles=[])
        result = await mode.scan_ahead()
        assert result == []

    async def test_scan_ahead_with_obstacles(self):
        obstacles = [
            Obstacle(label="chair", distance_m=1.5, direction="left", severity=Severity.WARNING),
        ]
        mode = self._make(obstacles=obstacles)
        result = await mode.scan_ahead()
        assert len(result) == 1
        mode.audio_cues.warning_tone.assert_awaited()

    async def test_scan_ahead_danger(self):
        obstacles = [
            Obstacle(label="car", distance_m=0.5, direction="center", severity=Severity.DANGER),
        ]
        mode = self._make(obstacles=obstacles)
        result = await mode.scan_ahead()
        assert len(result) == 1
        mode.audio_cues.danger_alert.assert_awaited()
        mode.haptics.triple_pulse.assert_awaited()


# ===========================================================================
# IdentifyMode
# ===========================================================================


class TestIdentifyMode:
    def _make(self, describe_result: str = "It's a red coffee mug.") -> IdentifyMode:
        vlm = MagicMock()
        vlm.describe = AsyncMock(return_value=describe_result)
        vlm.answer = AsyncMock(return_value="It's a label for aspirin.")
        return IdentifyMode(
            speaker=_mock_speaker(),
            haptics=_mock_haptics(),
            audio_cues=_mock_audio_cues(),
            camera=_mock_camera(),
            vlm=vlm,
        )

    async def test_activate(self):
        mode = self._make()
        await mode.activate()
        assert mode.is_active is True

    async def test_deactivate(self):
        mode = self._make()
        await mode.activate()
        await mode.deactivate()
        assert mode.is_active is False

    async def test_identify(self):
        mode = self._make()
        result = await mode.identify()
        assert "coffee mug" in result.lower()
        mode.audio_cues.chime.assert_awaited()

    async def test_identify_no_camera(self):
        mode = self._make()
        mode.camera.capture_frame = AsyncMock(return_value=None)
        result = await mode.identify()
        assert "camera" in result.lower()

    async def test_identify_empty_result(self):
        mode = self._make(describe_result="")
        result = await mode.identify()
        assert "try again" in result.lower()


# ===========================================================================
# EmergencyMode
# ===========================================================================


class TestEmergencyMode:
    def _make(self) -> EmergencyMode:
        vlm = MagicMock()
        vlm.describe = AsyncMock(return_value="A busy street corner near a pharmacy.")
        orientation = MagicMock()
        orientation.get_heading_description = AsyncMock(return_value="You are facing south")
        orientation.get_location_description = AsyncMock(return_value="At 37.7N, 122.4W. Facing south")
        return EmergencyMode(
            speaker=_mock_speaker(),
            haptics=_mock_haptics(),
            audio_cues=_mock_audio_cues(),
            camera=_mock_camera(),
            vlm=vlm,
            orientation=orientation,
        )

    async def test_activate(self):
        mode = self._make()
        await mode.activate()
        assert mode.is_active is True
        mode.haptics.triple_pulse.assert_awaited()
        mode.audio_cues.danger_alert.assert_awaited()

    async def test_deactivate(self):
        mode = self._make()
        await mode.activate()
        await mode.deactivate()
        assert mode.is_active is False

    async def test_locate(self):
        mode = self._make()
        result = await mode.locate()
        assert len(result) > 0
        mode.speaker.say_urgent.assert_awaited()

    async def test_locate_no_camera(self):
        mode = self._make()
        mode.camera.capture_frame = AsyncMock(return_value=None)
        result = await mode.locate()
        # Should still include orientation data
        assert len(result) > 0
