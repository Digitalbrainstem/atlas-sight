"""Gesture recognition — maps raw touch/motion events to semantic Gesture objects.

All feedback is non-visual.  The gesture vocabulary is deliberately simple so
that blind/visually-impaired users can learn it quickly and invoke every
command single-handedly.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from atlas_sight.data.models import (
    Gesture,
    GestureType,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Raw sensor events
# ---------------------------------------------------------------------------

@dataclass
class TouchEvent:
    """A single raw touch event from the touchscreen."""

    x: float
    y: float
    action: str  # "down", "up", "move"
    timestamp: float
    pointer_count: int = 1


@dataclass
class MotionEvent:
    """A single raw motion-sensor reading (accelerometer/gyro)."""

    accel_x: float
    accel_y: float
    accel_z: float
    timestamp: float


# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------

@dataclass
class GestureThresholds:
    """Tuneable thresholds for gesture detection."""

    double_tap_interval_sec: float = 0.35
    double_tap_max_drift_px: float = 40.0
    long_press_duration_sec: float = 0.8
    swipe_min_distance_px: float = 80.0
    swipe_max_off_axis_ratio: float = 0.6
    shake_magnitude_threshold: float = 18.0
    shake_window_sec: float = 0.5
    shake_min_peaks: int = 2
    two_finger_tap_max_duration_sec: float = 0.4


# ---------------------------------------------------------------------------
# Gesture → command mapping
# ---------------------------------------------------------------------------

GESTURE_COMMANDS: dict[GestureType, str] = {
    GestureType.DOUBLE_TAP: "describe_scene",
    GestureType.SWIPE_RIGHT: "read_text",
    GestureType.SWIPE_LEFT: "repeat_last",
    GestureType.SWIPE_UP: "more_detail",
    GestureType.SWIPE_DOWN: "navigation_mode",
    GestureType.SHAKE: "emergency_locate",
    GestureType.LONG_PRESS: "toggle_continuous",
    GestureType.TWO_FINGER_TAP: "identify_center_object",
}


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

# Callback type: receives a fully-formed Gesture and may be awaited.
OnGestureCallback = Callable[[Gesture], Awaitable[None]]


class GestureHandler:
    """Recognises gestures from raw touch / motion data.

    Usage::

        handler = GestureHandler()
        handler.on_gesture = my_async_callback
        await handler.process_touch(event)
    """

    def __init__(
        self,
        thresholds: GestureThresholds | None = None,
    ) -> None:
        self._thresholds = thresholds or GestureThresholds()

        # Public callback — set by the consumer.
        self.on_gesture: OnGestureCallback | None = None

        # Internal state for tap detection.
        self._last_down: TouchEvent | None = None
        self._last_tap_time: float = 0.0
        self._last_tap_pos: tuple[float, float] = (0.0, 0.0)
        self._pending_tap_task: asyncio.Task[None] | None = None

        # Internal state for long press.
        self._long_press_task: asyncio.Task[None] | None = None
        self._long_press_fired: bool = False

        # Internal state for two-finger tap.
        self._two_finger_down_time: float = 0.0

        # Motion history for shake detection.
        self._motion_history: deque[MotionEvent] = deque(maxlen=64)

    # -- public API --------------------------------------------------------

    async def process_touch(self, event: TouchEvent) -> None:
        """Ingest a raw touch event and fire ``on_gesture`` if recognised."""
        if event.action not in ("down", "up", "move"):
            log.warning("Unknown touch action %r — ignoring", event.action)
            return

        # Two-finger tap takes priority.
        if self._detect_two_finger_tap(event):
            await self._emit(GestureType.TWO_FINGER_TAP, event.timestamp)
            return

        if event.action == "down":
            self._last_down = event
            self._long_press_fired = False
            self._start_long_press_timer(event)

        elif event.action == "up":
            self._cancel_long_press_timer()

            if self._long_press_fired:
                # Already handled as long press — swallow the up.
                return

            # Check swipe first (large displacement).
            swipe = self._detect_swipe(event)
            if swipe is not None:
                await self._emit(swipe, event.timestamp)
                self._reset_tap_state()
                return

            # Otherwise, treat as a tap candidate.
            if self._detect_double_tap(event):
                self._cancel_pending_tap()
                await self._emit(GestureType.DOUBLE_TAP, event.timestamp)
                self._reset_tap_state()
            else:
                # Record this tap and wait to see if a second tap follows.
                self._last_tap_time = event.timestamp
                self._last_tap_pos = (event.x, event.y)

    async def process_motion(self, event: MotionEvent) -> None:
        """Ingest accelerometer data and detect shake gestures."""
        self._motion_history.append(event)
        if self._detect_shake(event):
            await self._emit(GestureType.SHAKE, event.timestamp)
            self._motion_history.clear()

    # -- detection helpers -------------------------------------------------

    def _detect_double_tap(self, event: TouchEvent) -> bool:
        """Return *True* if ``event`` is the second tap of a double-tap."""
        if self._last_tap_time == 0.0:
            return False

        dt = event.timestamp - self._last_tap_time
        if dt > self._thresholds.double_tap_interval_sec:
            return False

        dx = abs(event.x - self._last_tap_pos[0])
        dy = abs(event.y - self._last_tap_pos[1])
        drift = math.hypot(dx, dy)
        return drift <= self._thresholds.double_tap_max_drift_px

    def _detect_swipe(self, event: TouchEvent) -> GestureType | None:
        """Classify the swipe direction or return *None*."""
        if self._last_down is None:
            return None

        dx = event.x - self._last_down.x
        dy = event.y - self._last_down.y
        dist = math.hypot(dx, dy)

        if dist < self._thresholds.swipe_min_distance_px:
            return None

        abs_dx, abs_dy = abs(dx), abs(dy)

        # Ensure the swipe is predominantly in one axis.
        if abs_dx > abs_dy:
            if abs_dy / max(abs_dx, 1e-9) > self._thresholds.swipe_max_off_axis_ratio:
                return None
            return GestureType.SWIPE_RIGHT if dx > 0 else GestureType.SWIPE_LEFT
        else:
            if abs_dx / max(abs_dy, 1e-9) > self._thresholds.swipe_max_off_axis_ratio:
                return None
            return GestureType.SWIPE_DOWN if dy > 0 else GestureType.SWIPE_UP

    def _detect_long_press(self, event: TouchEvent) -> bool:
        """Return *True* if the finger has been held long enough."""
        if self._last_down is None:
            return False

        dx = abs(event.x - self._last_down.x)
        dy = abs(event.y - self._last_down.y)
        drift = math.hypot(dx, dy)
        if drift > self._thresholds.double_tap_max_drift_px:
            return False

        held = event.timestamp - self._last_down.timestamp
        return held >= self._thresholds.long_press_duration_sec

    def _detect_two_finger_tap(self, event: TouchEvent) -> bool:
        """Return *True* on a quick two-finger down+up."""
        if event.pointer_count < 2:
            self._two_finger_down_time = 0.0
            return False

        if event.action == "down":
            self._two_finger_down_time = event.timestamp
            return False

        if event.action == "up" and self._two_finger_down_time > 0.0:
            held = event.timestamp - self._two_finger_down_time
            self._two_finger_down_time = 0.0
            return held <= self._thresholds.two_finger_tap_max_duration_sec

        return False

    def _detect_shake(self, event: MotionEvent) -> bool:
        """Return *True* when the recent motion history contains a shake."""
        th = self._thresholds
        cutoff = event.timestamp - th.shake_window_sec
        peaks = 0
        for m in self._motion_history:
            if m.timestamp < cutoff:
                continue
            mag = math.sqrt(m.accel_x ** 2 + m.accel_y ** 2 + m.accel_z ** 2)
            if mag >= th.shake_magnitude_threshold:
                peaks += 1
        return peaks >= th.shake_min_peaks

    # -- internal helpers --------------------------------------------------

    async def _emit(self, gesture_type: GestureType, timestamp: float) -> None:
        """Build a ``Gesture`` and invoke the callback."""
        gesture = Gesture(
            gesture_type=gesture_type,
            timestamp=timestamp,
            metadata={"command": GESTURE_COMMANDS.get(gesture_type, "unknown")},
        )
        log.info(
            "Gesture recognised: %s → %s",
            gesture_type.value,
            gesture.metadata.get("command"),
        )
        if self.on_gesture is not None:
            await self.on_gesture(gesture)

    def _reset_tap_state(self) -> None:
        self._last_tap_time = 0.0
        self._last_tap_pos = (0.0, 0.0)

    # -- long-press timer --------------------------------------------------

    def _start_long_press_timer(self, event: TouchEvent) -> None:
        self._cancel_long_press_timer()

        async def _wait() -> None:
            await asyncio.sleep(self._thresholds.long_press_duration_sec)
            if self._last_down is not None and not self._long_press_fired:
                self._long_press_fired = True
                await self._emit(GestureType.LONG_PRESS, time.time())

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._long_press_task = loop.create_task(_wait())

    def _cancel_long_press_timer(self) -> None:
        if self._long_press_task is not None and not self._long_press_task.done():
            self._long_press_task.cancel()
        self._long_press_task = None

    # -- pending single-tap timer (unused yet, reserved for future) --------

    def _cancel_pending_tap(self) -> None:
        if self._pending_tap_task is not None and not self._pending_tap_task.done():
            self._pending_tap_task.cancel()
        self._pending_tap_task = None
