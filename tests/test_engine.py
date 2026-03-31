"""Tests for atlas_sight.core.engine.SightEngine."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from atlas_sight.config import ContentType, Mode, SightConfig, SpeedProfile, Verbosity, VoiceSettings
from atlas_sight.core.engine import SightEngine, _CYCLEABLE_MODES
from atlas_sight.data.models import (
    Gesture,
    GestureType,
    Obstacle,
    Severity,
    VoiceCommand,
)


def _cmd(intent: str, **params: object) -> VoiceCommand:
    """Build a VoiceCommand with given intent."""
    return VoiceCommand(raw_text="test", intent=intent, parameters=dict(params))


def _engine() -> SightEngine:
    """Create a SightEngine with mocked subsystems (bypasses _init_subsystems)."""
    engine = SightEngine(SightConfig())
    engine._running = True

    # Mock subsystems
    engine._speaker = MagicMock()
    engine._speaker.say = AsyncMock()
    engine._speaker.say_urgent = AsyncMock()
    engine._speaker.stop_speaking = AsyncMock()
    engine._speaker.set_speed = MagicMock()
    engine._speaker.set_volume = MagicMock()
    engine._speaker.reset_speed = MagicMock()
    engine._speaker.go_max_speed = MagicMock()
    engine._speaker.speed = 1.0
    engine._speaker.speed_profile = SpeedProfile()

    engine._camera = MagicMock()
    engine._camera.capture = AsyncMock(return_value=b"\x00\x01")
    engine._camera.stop = AsyncMock()

    engine._listener = MagicMock()
    engine._listener.start = AsyncMock()
    engine._listener.stop = AsyncMock()

    engine._haptics = MagicMock()
    engine._haptics.vibrate = AsyncMock()

    engine._audio_cues = MagicMock()
    engine._audio_cues.play = AsyncMock()

    engine._vlm = MagicMock()
    engine._vlm.describe = AsyncMock(return_value="A room.")

    engine._context = MagicMock()
    engine._context.get_context_prompt = MagicMock(return_value="")
    engine._context.was_recently_described = MagicMock(return_value=False)
    engine._context.add = MagicMock()
    engine._context.last_description = "Last thing I said."

    engine._scene_analyzer = MagicMock()
    engine._scene_analyzer.analyze = AsyncMock()

    engine._history = MagicMock()
    engine._history.bookmark_last = MagicMock(return_value=MagicMock())

    engine._command_parser = MagicMock()
    engine._gesture_handler = MagicMock()
    engine._gesture_handler.stop = AsyncMock()

    return engine


# ===========================================================================
# Voice command dispatch
# ===========================================================================


class TestVoiceDispatch:
    async def test_describe(self):
        e = _engine()
        e.describe_scene = AsyncMock()
        await e.process_voice(_cmd("describe"))
        e.describe_scene.assert_awaited_once()

    async def test_read_text(self):
        e = _engine()
        e.read_text = AsyncMock()
        await e.process_voice(_cmd("read_text"))
        e.read_text.assert_awaited_once()

    async def test_check_ahead(self):
        e = _engine()
        e.check_obstacles = AsyncMock()
        await e.process_voice(_cmd("check_ahead"))
        e.check_obstacles.assert_awaited_once()

    async def test_locate(self):
        e = _engine()
        e.emergency_locate = AsyncMock()
        await e.process_voice(_cmd("locate"))
        e.emergency_locate.assert_awaited_once()

    async def test_navigate(self):
        e = _engine()
        e.set_mode = AsyncMock()
        await e.process_voice(_cmd("navigate"))
        e.set_mode.assert_awaited_once_with(Mode.NAVIGATE)

    async def test_louder(self):
        e = _engine()
        e.adjust_volume = AsyncMock()
        await e.process_voice(_cmd("louder"))
        e.adjust_volume.assert_awaited_once()
        args = e.adjust_volume.call_args[0]
        assert args[0] > 0

    async def test_softer(self):
        e = _engine()
        e.adjust_volume = AsyncMock()
        await e.process_voice(_cmd("softer"))
        e.adjust_volume.assert_awaited_once()
        args = e.adjust_volume.call_args[0]
        assert args[0] < 0

    async def test_faster(self):
        e = _engine()
        e.adjust_speed = AsyncMock()
        await e.process_voice(_cmd("faster"))
        e.adjust_speed.assert_awaited_once()
        args = e.adjust_speed.call_args[0]
        assert args[0] > 0

    async def test_slower(self):
        e = _engine()
        e.adjust_speed = AsyncMock()
        await e.process_voice(_cmd("slower"))
        e.adjust_speed.assert_awaited_once()
        args = e.adjust_speed.call_args[0]
        assert args[0] < 0

    async def test_normal_speed(self):
        e = _engine()
        e.normal_speed = AsyncMock()
        await e.process_voice(_cmd("normal_speed"))
        e.normal_speed.assert_awaited_once()

    async def test_max_speed(self):
        e = _engine()
        e.max_speed = AsyncMock()
        await e.process_voice(_cmd("max_speed"))
        e.max_speed.assert_awaited_once()

    async def test_more_detail(self):
        e = _engine()
        e.set_verbosity = AsyncMock()
        await e.process_voice(_cmd("more_detail"))
        e.set_verbosity.assert_awaited_once_with(Verbosity.DETAILED)

    async def test_less_detail(self):
        e = _engine()
        e.set_verbosity = AsyncMock()
        await e.process_voice(_cmd("less_detail"))
        e.set_verbosity.assert_awaited_once_with(Verbosity.BRIEF)

    async def test_remember(self):
        e = _engine()
        e.remember_scene = AsyncMock()
        await e.process_voice(_cmd("remember"))
        e.remember_scene.assert_awaited_once()

    async def test_repeat(self):
        e = _engine()
        e.repeat_last = AsyncMock()
        await e.process_voice(_cmd("repeat"))
        e.repeat_last.assert_awaited_once()

    async def test_stop(self):
        e = _engine()
        await e.process_voice(_cmd("stop"))
        e._speaker.say.assert_awaited()

    async def test_help(self):
        e = _engine()
        await e.process_voice(_cmd("help"))
        e._speaker.say.assert_awaited()

    async def test_unknown(self):
        e = _engine()
        await e.process_voice(_cmd("unknown"))
        e._speaker.say.assert_awaited()
        call_text = e._speaker.say.call_args[0][0]
        assert "didn't understand" in call_text.lower()


# ===========================================================================
# Gesture dispatch
# ===========================================================================


class TestGestureDispatch:
    def _gesture(self, gesture_type: GestureType) -> Gesture:
        return Gesture(gesture_type=gesture_type)

    async def test_double_tap_describes(self):
        e = _engine()
        e.describe_scene = AsyncMock()
        await e.process_gesture(self._gesture(GestureType.DOUBLE_TAP))
        e.describe_scene.assert_awaited_once()

    async def test_swipe_right_cycles_mode(self):
        e = _engine()
        e.set_mode = AsyncMock()
        await e.process_gesture(self._gesture(GestureType.SWIPE_RIGHT))
        e.set_mode.assert_awaited_once()

    async def test_swipe_left_cycles_mode_back(self):
        e = _engine()
        e.set_mode = AsyncMock()
        await e.process_gesture(self._gesture(GestureType.SWIPE_LEFT))
        e.set_mode.assert_awaited_once()

    async def test_swipe_up_volume_up(self):
        e = _engine()
        e.adjust_volume = AsyncMock()
        await e.process_gesture(self._gesture(GestureType.SWIPE_UP))
        e.adjust_volume.assert_awaited_once()

    async def test_swipe_down_volume_down(self):
        e = _engine()
        e.adjust_volume = AsyncMock()
        await e.process_gesture(self._gesture(GestureType.SWIPE_DOWN))
        e.adjust_volume.assert_awaited_once()

    async def test_shake_emergency(self):
        e = _engine()
        e.emergency_locate = AsyncMock()
        await e.process_gesture(self._gesture(GestureType.SHAKE))
        e.emergency_locate.assert_awaited_once()

    async def test_long_press_read(self):
        e = _engine()
        e.read_text = AsyncMock()
        await e.process_gesture(self._gesture(GestureType.LONG_PRESS))
        e.read_text.assert_awaited_once()

    async def test_two_finger_tap_obstacles(self):
        e = _engine()
        e.check_obstacles = AsyncMock()
        await e.process_gesture(self._gesture(GestureType.TWO_FINGER_TAP))
        e.check_obstacles.assert_awaited_once()


# ===========================================================================
# Mode switching
# ===========================================================================


class TestModeSwitching:
    async def test_set_mode(self):
        e = _engine()
        await e.set_mode(Mode.READ)
        assert e._current_mode_enum == Mode.READ
        e._speaker.say.assert_awaited()

    async def test_set_same_mode(self):
        e = _engine()
        e._current_mode_enum = Mode.EXPLORE
        await e.set_mode(Mode.EXPLORE)
        call_text = e._speaker.say.call_args[0][0]
        assert "already" in call_text.lower()

    def test_next_mode_cycles(self):
        e = _engine()
        e._current_mode_enum = Mode.EXPLORE
        next_mode = e._next_mode(1)
        assert next_mode == _CYCLEABLE_MODES[1]

    def test_next_mode_wraps(self):
        e = _engine()
        e._current_mode_enum = _CYCLEABLE_MODES[-1]
        next_mode = e._next_mode(1)
        assert next_mode == _CYCLEABLE_MODES[0]

    def test_next_mode_backwards(self):
        e = _engine()
        e._current_mode_enum = _CYCLEABLE_MODES[0]
        prev_mode = e._next_mode(-1)
        assert prev_mode == _CYCLEABLE_MODES[-1]


# ===========================================================================
# Settings
# ===========================================================================


class TestSettingsAdjustment:
    async def test_set_verbosity(self):
        e = _engine()
        await e.set_verbosity(Verbosity.DETAILED)
        assert e._config.verbosity == Verbosity.DETAILED
        e._speaker.say.assert_awaited()

    async def test_remember_scene(self):
        e = _engine()
        await e.remember_scene()
        e._history.bookmark_last.assert_called_once()
        e._speaker.say.assert_awaited()

    async def test_remember_scene_nothing(self):
        e = _engine()
        e._history.bookmark_last = MagicMock(return_value=None)
        await e.remember_scene()
        call_text = e._speaker.say.call_args[0][0]
        assert "nothing" in call_text.lower()

    async def test_repeat_last(self):
        e = _engine()
        await e.repeat_last()
        e._speaker.say.assert_awaited()
        call_text = e._speaker.say.call_args[0][0]
        assert call_text == "Last thing I said."

    async def test_repeat_last_empty(self):
        e = _engine()
        e._context.last_description = ""
        await e.repeat_last()
        call_text = e._speaker.say.call_args[0][0]
        assert "nothing" in call_text.lower()


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    async def test_voice_exception_spoken(self):
        e = _engine()
        e._handle_voice_command = AsyncMock(side_effect=RuntimeError("boom"))
        # process_voice catches and speaks
        await e.process_voice(_cmd("describe"))
        e._speaker.say.assert_awaited()
        call_text = e._speaker.say.call_args[0][0]
        assert "sorry" in call_text.lower()

    async def test_gesture_exception_spoken(self):
        e = _engine()
        e._handle_gesture = AsyncMock(side_effect=RuntimeError("boom"))
        await e.process_gesture(Gesture(gesture_type=GestureType.DOUBLE_TAP))
        e._speaker.say.assert_awaited()
        call_text = e._speaker.say.call_args[0][0]
        assert "sorry" in call_text.lower()

    async def test_not_running_skips(self):
        e = _engine()
        e._running = False
        e._handle_voice_command = AsyncMock()
        await e.process_voice(_cmd("describe"))
        e._handle_voice_command.assert_not_awaited()


# ===========================================================================
# Format obstacle warnings
# ===========================================================================


class TestFormatObstacleWarnings:
    def test_empty(self):
        assert SightEngine._format_obstacle_warnings([]) == "Path is clear."

    def test_dangerous_first(self):
        obstacles = [
            Obstacle(label="chair", distance_m=1.5, direction="left", severity=Severity.WARNING),
            Obstacle(label="car", distance_m=0.5, direction="center", severity=Severity.DANGER),
        ]
        result = SightEngine._format_obstacle_warnings(obstacles)
        # Danger should come before warning
        car_pos = result.find("car")
        chair_pos = result.find("chair")
        assert car_pos < chair_pos

    def test_close_distance_in_centimeters(self):
        obstacles = [
            Obstacle(label="pole", distance_m=0.5, direction="right", severity=Severity.DANGER),
        ]
        result = SightEngine._format_obstacle_warnings(obstacles)
        assert "centimeters" in result

    def test_far_distance_in_meters(self):
        obstacles = [
            Obstacle(label="table", distance_m=2.0, direction="left", severity=Severity.WARNING),
        ]
        result = SightEngine._format_obstacle_warnings(obstacles)
        assert "meters" in result
