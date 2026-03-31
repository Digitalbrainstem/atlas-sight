"""Haptic feedback — vibration patterns for non-visual interaction.

All platform-specific vibration calls are isolated behind ``_vibrate`` which
is stubbed with a log message when running on hardware that lacks a vibration
motor.  This keeps the module importable and testable everywhere.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from atlas_sight.config import HapticPattern

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-defined vibration patterns
# ---------------------------------------------------------------------------

PREDEFINED_PATTERNS: dict[str, HapticPattern] = {
    "acknowledge": HapticPattern(
        name="acknowledge",
        pulses=[(80, 0)],
    ),
    "warning": HapticPattern(
        name="warning",
        pulses=[(120, 60), (120, 60), (120, 0)],
    ),
    "danger": HapticPattern(
        name="danger",
        pulses=[(50, 30), (50, 30), (50, 30), (50, 30), (50, 30), (50, 0)],
    ),
    "heartbeat": HapticPattern(
        name="heartbeat",
        pulses=[(100, 120), (100, 600)],
    ),
    "success": HapticPattern(
        name="success",
        pulses=[(60, 80), (60, 0)],
    ),
    "navigate": HapticPattern(
        name="navigate",
        pulses=[(70, 100), (70, 100), (70, 0)],
    ),
}


# ---------------------------------------------------------------------------
# Feedback controller
# ---------------------------------------------------------------------------

class HapticFeedback:
    """Controls vibration-based feedback for a blind/VI user.

    Usage::

        haptics = HapticFeedback()
        await haptics.double_pulse()          # acknowledge a command
        await haptics.heartbeat(active=True)  # continuous-mode indicator
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._stopped = False

    # -- enabled property --------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            # Silently stop any running heartbeat when disabled.
            self._cancel_heartbeat()

    # -- simple pulses -----------------------------------------------------

    async def pulse(self, duration_ms: int = 100) -> None:
        """Single vibration pulse."""
        if not self._enabled:
            return
        await self._vibrate(max(1, duration_ms))

    async def double_pulse(self) -> None:
        """Two quick pulses — command acknowledged."""
        if not self._enabled:
            return
        await self._vibrate(60)
        await asyncio.sleep(0.08)
        await self._vibrate(60)

    async def triple_pulse(self) -> None:
        """Three pulses — warning / attention."""
        if not self._enabled:
            return
        await self._vibrate(120)
        await asyncio.sleep(0.06)
        await self._vibrate(120)
        await asyncio.sleep(0.06)
        await self._vibrate(120)

    # -- patterns ----------------------------------------------------------

    async def play_pattern(self, pattern: HapticPattern) -> None:
        """Play an arbitrary ``HapticPattern``."""
        if not self._enabled:
            return
        log.debug("Playing haptic pattern %r (%d pulses)", pattern.name, len(pattern.pulses))
        for on_ms, off_ms in pattern.pulses:
            if self._stopped:
                break
            await self._vibrate(on_ms)
            if off_ms > 0:
                await asyncio.sleep(off_ms / 1000.0)

    # -- heartbeat ---------------------------------------------------------

    async def heartbeat(self, active: bool = True) -> None:
        """Start or stop a repeating heartbeat vibration.

        The heartbeat lets the user know that continuous mode is running even
        when there is nothing to announce.
        """
        if active:
            if self._heartbeat_task is not None and not self._heartbeat_task.done():
                return  # already beating
            self._stopped = False
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                log.warning("No running event loop — cannot start heartbeat")
                return
            self._heartbeat_task = loop.create_task(self._heartbeat_loop())
            log.info("Heartbeat started")
        else:
            self._cancel_heartbeat()
            log.info("Heartbeat stopped")

    async def _heartbeat_loop(self) -> None:
        """Internal loop that repeats the heartbeat pattern."""
        pattern = PREDEFINED_PATTERNS["heartbeat"]
        try:
            while self._enabled and not self._stopped:
                await self.play_pattern(pattern)
                # Brief silence between heartbeat cycles.
                await asyncio.sleep(0.6)
        except asyncio.CancelledError:
            pass

    # -- stop --------------------------------------------------------------

    async def stop(self) -> None:
        """Stop all haptic output immediately."""
        self._stopped = True
        self._cancel_heartbeat()
        log.info("Haptics stopped")

    # -- platform vibration stub -------------------------------------------

    async def _vibrate(self, duration_ms: int) -> None:
        """Trigger the platform vibration motor.

        This is a stub that logs the intention.  On real hardware, replace
        with the appropriate platform call (Android ``Vibrator`` service,
        iOS ``UIImpactFeedbackGenerator``, etc.).
        """
        log.debug("_vibrate(%d ms)", duration_ms)
        # Simulate the vibration duration so callers that depend on timing
        # still behave correctly in tests and on desktop.
        await asyncio.sleep(duration_ms / 1000.0)

    # -- internal helpers --------------------------------------------------

    def _cancel_heartbeat(self) -> None:
        self._stopped = True
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        self._heartbeat_task = None
