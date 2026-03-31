"""Proximity-alert engine that turns detected objects into spoken warnings.

Designed for real-time use on a phone camera feed: every frame produces a
list of :class:`DetectedObject` items from the vision model, and this module
decides *what to say* and *how urgently*.

Warning style guide
-------------------
* **Single obstacle** — ``"Caution: chair about 1 metre ahead on your right"``
* **Multiple obstacles** — ``"Warning: person 2 metres ahead, and a table on your left"``
* **Danger** — ``"Stop! Stairs directly ahead, less than 1 metre"``
* **Nothing to report** — returns ``None`` (caller stays silent).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from atlas_sight.config import NavigationSettings
from atlas_sight.data.models import (
    BoundingBox,
    DetectedObject,
    Obstacle,
    Severity,
)

logger = logging.getLogger(__name__)

# Bbox-area → distance mapping constants.  A full-frame object (area ≈ 1.0)
# is assumed to be at ~0.3 m; a tiny detection (area → 0) maps toward the
# far reference distance.
_NEAR_REF_M = 0.3
_FAR_REF_M = 12.0
_MIN_AREA = 0.001  # clamp to avoid division by zero


class ObstacleWarner:
    """Convert raw object detections into actionable spoken warnings.

    Parameters
    ----------
    settings:
        Shared navigation thresholds (warn distance, danger distance, …).
    """

    def __init__(self, settings: NavigationSettings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self, objects: list[DetectedObject],
    ) -> list[Obstacle]:
        """Convert detected objects to ranked obstacles.

        Only objects whose :pyattr:`is_obstacle` flag is ``True`` are
        promoted.  The returned list is sorted by severity (danger first),
        then by ascending distance.
        """
        if not objects:
            return []

        obstacles: list[Obstacle] = []
        for obj in objects:
            if not obj.is_obstacle:
                continue

            distance = self._estimate_distance(obj)
            severity = self._assign_severity(distance)

            obstacles.append(
                Obstacle(
                    label=obj.label,
                    distance_m=distance,
                    direction=self._classify_direction(obj.bbox),
                    severity=severity,
                    bbox=obj.bbox,
                )
            )

        obstacles.sort(key=self._sort_key)

        logger.debug(
            "analyzed %d objects → %d obstacles (danger=%d, warning=%d)",
            len(objects),
            len(obstacles),
            sum(1 for o in obstacles if o.severity is Severity.DANGER),
            sum(1 for o in obstacles if o.severity is Severity.WARNING),
        )
        return obstacles

    async def get_warning_message(
        self, obstacles: list[Obstacle],
    ) -> str | None:
        """Build a natural-language warning from a list of obstacles.

        Returns ``None`` when there is nothing worth reporting (empty list
        or every obstacle is ``INFO`` severity).
        """
        # Only warn about WARNING and DANGER obstacles.
        actionable = [o for o in obstacles if o.severity is not Severity.INFO]
        if not actionable:
            return None

        # Re-sort to guarantee danger-first, nearest-first ordering.
        actionable.sort(key=self._sort_key)

        has_danger = any(o.severity is Severity.DANGER for o in actionable)

        if len(actionable) == 1:
            return self._format_single(actionable[0])

        return self._format_multiple(actionable, has_danger)

    # ------------------------------------------------------------------
    # Distance / direction heuristics
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_distance(obj: DetectedObject) -> float:
        """Estimate distance in metres from bounding-box area.

        If the detection already carries a measured ``distance_m`` (e.g.
        from a LiDAR sensor) we trust that value.  Otherwise we fall back
        to an inverse-area heuristic: a larger bounding box implies a
        closer object.
        """
        if obj.distance_m is not None and obj.distance_m > 0:
            return obj.distance_m

        area = max(obj.bbox.area, _MIN_AREA)
        # Inverse-sqrt gives a perceptually reasonable curve: doubling
        # the apparent size roughly halves the estimated distance.
        return _NEAR_REF_M + (_FAR_REF_M - _NEAR_REF_M) * (1.0 - area ** 0.5)

    @staticmethod
    def _classify_direction(bbox: BoundingBox) -> str:
        """Map horizontal centre of a bounding box to left / centre / right."""
        cx = bbox.center[0]
        if cx < 0.33:
            return "left"
        if cx < 0.67:
            return "center"
        return "right"

    def _assign_severity(self, distance_m: float) -> Severity:
        """Assign a severity tier based on distance thresholds."""
        if distance_m < self._settings.obstacle_danger_distance_m:
            return Severity.DANGER
        if distance_m < self._settings.obstacle_warn_distance_m:
            return Severity.WARNING
        return Severity.INFO

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_obstacle(obstacle: Obstacle) -> str:
        """Short spoken fragment for a single obstacle.

        Examples
        -------
        * ``"person, 2 metres ahead on your left"``
        * ``"stairs directly ahead, less than 1 metre"``
        """
        dist_text = _distance_text(obstacle.distance_m)
        dir_text = _direction_text(obstacle.direction)
        return f"{obstacle.label}, {dist_text}{dir_text}"

    def _format_single(self, obstacle: Obstacle) -> str:
        """Full sentence for exactly one obstacle."""
        prefix = _severity_prefix(obstacle.severity)
        return f"{prefix}{self._format_obstacle(obstacle)}"

    def _format_multiple(
        self, obstacles: list[Obstacle], has_danger: bool,
    ) -> str:
        """Natural sentence combining multiple obstacles."""
        prefix = "Stop! " if has_danger else "Warning: "
        parts = [self._format_obstacle(o) for o in obstacles]

        if len(parts) == 2:
            body = f"{parts[0]}, and {parts[1]}"
        else:
            body = ", ".join(parts[:-1]) + f", and {parts[-1]}"

        return f"{prefix}{body}"

    @staticmethod
    def _format_obstacles(obstacles: list[Obstacle]) -> str:
        """Comma-joined labels for logging / debugging."""
        return ", ".join(
            f"{o.label}({o.severity.name} {o.distance_m:.1f}m {o.direction})"
            for o in obstacles
        )

    # ------------------------------------------------------------------
    # Sort key
    # ------------------------------------------------------------------

    @staticmethod
    def _sort_key(obstacle: Obstacle) -> tuple[int, float]:
        """Sort by severity descending (DANGER=0), then distance ascending."""
        severity_order = {
            Severity.DANGER: 0,
            Severity.WARNING: 1,
            Severity.INFO: 2,
        }
        return severity_order.get(obstacle.severity, 3), obstacle.distance_m


# ------------------------------------------------------------------
# Module-level formatting utilities
# ------------------------------------------------------------------

def _distance_text(metres: float) -> str:
    """Speech-friendly distance, e.g. ``"about 2 metres ahead"``."""
    if metres < 1.0:
        return "less than 1 metre ahead"
    rounded = round(metres)
    unit = "metre" if rounded == 1 else "metres"
    return f"about {rounded} {unit} ahead"


def _direction_text(direction: str) -> str:
    """Append a direction qualifier (empty for centre/ahead)."""
    if direction == "center":
        return ""
    return f" on your {direction}"


def _severity_prefix(severity: Severity) -> str:
    """Spoken prefix that conveys urgency."""
    if severity is Severity.DANGER:
        return "Stop! "
    if severity is Severity.WARNING:
        return "Caution: "
    return ""
