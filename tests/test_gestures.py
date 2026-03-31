"""Tests for atlas_sight.interaction.gestures.GestureHandler."""
from __future__ import annotations

import math
from unittest.mock import AsyncMock

import pytest

from atlas_sight.data.models import GestureType
from atlas_sight.interaction.gestures import (
    GestureHandler,
    GestureThresholds,
    MotionEvent,
    TouchEvent,
)


@pytest.fixture()
def handler() -> GestureHandler:
    return GestureHandler()


# ---------------------------------------------------------------------------
# Double tap
# ---------------------------------------------------------------------------


class TestDoubleTap:
    async def test_double_tap_fires_callback(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        # First tap: down + up
        await handler.process_touch(TouchEvent(x=100, y=100, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=100, y=100, action="up", timestamp=now + 0.05))

        # Second tap within interval
        await handler.process_touch(TouchEvent(x=100, y=100, action="down", timestamp=now + 0.15))
        await handler.process_touch(TouchEvent(x=102, y=102, action="up", timestamp=now + 0.2))

        callback.assert_called_once()
        gesture = callback.call_args[0][0]
        assert gesture.gesture_type == GestureType.DOUBLE_TAP

    async def test_double_tap_too_slow(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(TouchEvent(x=100, y=100, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=100, y=100, action="up", timestamp=now + 0.05))

        # Second tap after interval expires
        await handler.process_touch(TouchEvent(x=100, y=100, action="down", timestamp=now + 1.0))
        await handler.process_touch(TouchEvent(x=100, y=100, action="up", timestamp=now + 1.05))

        callback.assert_not_called()

    async def test_double_tap_too_far_apart(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(TouchEvent(x=100, y=100, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=100, y=100, action="up", timestamp=now + 0.05))

        # Second tap too far away
        await handler.process_touch(TouchEvent(x=300, y=300, action="down", timestamp=now + 0.15))
        await handler.process_touch(TouchEvent(x=300, y=300, action="up", timestamp=now + 0.2))

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# Swipe detection
# ---------------------------------------------------------------------------


class TestSwipeDetection:
    async def test_swipe_right(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(TouchEvent(x=100, y=200, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=300, y=200, action="up", timestamp=now + 0.2))

        callback.assert_called_once()
        assert callback.call_args[0][0].gesture_type == GestureType.SWIPE_RIGHT

    async def test_swipe_left(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(TouchEvent(x=300, y=200, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=100, y=200, action="up", timestamp=now + 0.2))

        callback.assert_called_once()
        assert callback.call_args[0][0].gesture_type == GestureType.SWIPE_LEFT

    async def test_swipe_up(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(TouchEvent(x=200, y=300, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=200, y=100, action="up", timestamp=now + 0.2))

        callback.assert_called_once()
        assert callback.call_args[0][0].gesture_type == GestureType.SWIPE_UP

    async def test_swipe_down(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(TouchEvent(x=200, y=100, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=200, y=300, action="up", timestamp=now + 0.2))

        callback.assert_called_once()
        assert callback.call_args[0][0].gesture_type == GestureType.SWIPE_DOWN

    async def test_swipe_too_short(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(TouchEvent(x=100, y=100, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=110, y=100, action="up", timestamp=now + 0.2))

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# Shake detection
# ---------------------------------------------------------------------------


class TestShakeDetection:
    async def test_shake_detected(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        # Feed high-magnitude accelerometer readings within the shake window
        for i in range(5):
            await handler.process_motion(MotionEvent(
                accel_x=20.0,
                accel_y=0.0,
                accel_z=0.0,
                timestamp=now + i * 0.05,
            ))

        callback.assert_called()
        gesture = callback.call_args[0][0]
        assert gesture.gesture_type == GestureType.SHAKE

    async def test_no_shake_low_magnitude(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        for i in range(5):
            await handler.process_motion(MotionEvent(
                accel_x=2.0,
                accel_y=2.0,
                accel_z=2.0,
                timestamp=now + i * 0.05,
            ))

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# Two-finger tap
# ---------------------------------------------------------------------------


class TestTwoFingerTap:
    async def test_two_finger_tap(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(
            TouchEvent(x=100, y=100, action="down", timestamp=now, pointer_count=2)
        )
        await handler.process_touch(
            TouchEvent(x=100, y=100, action="up", timestamp=now + 0.2, pointer_count=2)
        )

        callback.assert_called_once()
        assert callback.call_args[0][0].gesture_type == GestureType.TWO_FINGER_TAP

    async def test_two_finger_tap_too_long(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback

        now = 1000.0
        await handler.process_touch(
            TouchEvent(x=100, y=100, action="down", timestamp=now, pointer_count=2)
        )
        await handler.process_touch(
            TouchEvent(x=100, y=100, action="up", timestamp=now + 1.0, pointer_count=2)
        )

        callback.assert_not_called()


# ---------------------------------------------------------------------------
# Callback not set
# ---------------------------------------------------------------------------


class TestNoCallback:
    async def test_no_callback_no_error(self, handler: GestureHandler):
        """Gesture detection works even without a callback."""
        now = 1000.0
        await handler.process_touch(TouchEvent(x=100, y=100, action="down", timestamp=now))
        await handler.process_touch(TouchEvent(x=100, y=100, action="up", timestamp=now + 0.05))
        await handler.process_touch(TouchEvent(x=100, y=100, action="down", timestamp=now + 0.15))
        await handler.process_touch(TouchEvent(x=100, y=100, action="up", timestamp=now + 0.2))
        # No assertion needed — just verify no exception

    async def test_unknown_action_ignored(self, handler: GestureHandler):
        callback = AsyncMock()
        handler.on_gesture = callback
        await handler.process_touch(
            TouchEvent(x=0, y=0, action="hover", timestamp=1000.0)
        )
        callback.assert_not_called()
