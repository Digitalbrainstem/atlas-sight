"""Compass, GPS, and landmark awareness for offline navigation.

Provides heading descriptions, human-readable location summaries, and a
personal landmark store so users can save and recall meaningful locations
(e.g. "front door", "bus stop") without any cloud dependency.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import replace

from atlas_sight.config import NavigationSettings
from atlas_sight.data.models import NavPoint, Orientation

logger = logging.getLogger(__name__)

# Mean Earth radius in metres (WGS-84 volumetric mean).
_EARTH_RADIUS_M = 6_371_008.8

# Eight-point compass rose, each segment spans 45°.
_COMPASS_POINTS: list[tuple[float, str]] = [
    (22.5, "north"),
    (67.5, "north-east"),
    (112.5, "east"),
    (157.5, "south-east"),
    (202.5, "south"),
    (247.5, "south-west"),
    (292.5, "west"),
    (337.5, "north-west"),
]


class OrientationHelper:
    """Sensor-driven orientation and landmark management.

    Parameters
    ----------
    settings:
        Shared navigation configuration (distances, intervals, etc.).
    """

    def __init__(self, settings: NavigationSettings) -> None:
        self._settings = settings
        self._landmarks: list[NavPoint] = []
        self._current = Orientation(
            heading_degrees=0.0,
            latitude=0.0,
            longitude=0.0,
            altitude_m=0.0,
            accuracy_m=-1.0,  # negative ⇒ no fix yet
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_orientation(self) -> Orientation:
        """Return the latest device orientation.

        On real hardware this would read the magnetometer / GNSS chipset.
        The stub keeps the last-known value so callers always get a
        coherent snapshot even when sensors are unavailable.
        """
        # TODO: wire to platform-specific sensor APIs (Android/iOS).
        logger.debug("orientation: heading=%.1f°, loc=(%s, %s), accuracy=%.1fm",
                      self._current.heading_degrees,
                      self._current.latitude,
                      self._current.longitude,
                      self._current.accuracy_m)
        return self._current

    async def get_heading_description(self) -> str:
        """Human-readable compass direction, e.g. *"You are facing north-east"*."""
        orientation = await self.get_orientation()
        compass = self._heading_to_compass(orientation.heading_degrees)
        return f"You are facing {compass}"

    async def get_location_description(self) -> str:
        """Human-readable summary of where the user is right now.

        Includes the nearest landmark when one is close enough to be
        useful (within 50 m) so the user hears e.g.
        *"Near front door, facing south"* instead of raw coordinates.
        """
        orientation = await self.get_orientation()

        if not orientation.has_location:
            compass = self._heading_to_compass(orientation.heading_degrees)
            return f"Location unavailable. {self._heading_text(compass)}"

        compass = self._heading_to_compass(orientation.heading_degrees)

        nearest = await self.get_nearest_landmark()
        if nearest is not None:
            landmark, distance = nearest
            if distance < 50.0:
                return (
                    f"Near {landmark.name}, about {self._round_distance(distance)} away. "
                    f"{self._heading_text(compass)}"
                )

        lat_dir = "north" if orientation.latitude >= 0 else "south"
        lon_dir = "east" if orientation.longitude >= 0 else "west"
        return (
            f"At {abs(orientation.latitude):.4f}° {lat_dir}, "
            f"{abs(orientation.longitude):.4f}° {lon_dir}. "
            f"{self._heading_text(compass)}"
        )

    async def save_landmark(self, name: str) -> NavPoint:
        """Bookmark the current location as a named landmark.

        Raises
        ------
        RuntimeError
            If the device has no GPS fix yet.
        """
        orientation = await self.get_orientation()

        if not orientation.has_location:
            raise RuntimeError("Cannot save landmark — no GPS fix available")

        point = NavPoint(
            name=name,
            latitude=orientation.latitude,
            longitude=orientation.longitude,
            description=f"Saved at heading {orientation.heading_degrees:.0f}°",
            timestamp=time.time(),
        )
        self._landmarks.append(point)
        logger.info("landmark saved: %s at (%.6f, %.6f)",
                     name, point.latitude, point.longitude)
        return point

    async def get_nearest_landmark(self) -> tuple[NavPoint, float] | None:
        """Return the closest saved landmark and its distance in metres.

        Returns ``None`` when there are no landmarks or no GPS fix.
        """
        orientation = await self.get_orientation()

        if not orientation.has_location or not self._landmarks:
            return None

        best: NavPoint | None = None
        best_dist = math.inf

        for lm in self._landmarks:
            d = self._distance_between(
                orientation.latitude, orientation.longitude,
                lm.latitude, lm.longitude,
            )
            if d < best_dist:
                best_dist = d
                best = lm

        if best is None:  # pragma: no cover — defensive
            return None
        return best, best_dist

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _heading_to_compass(degrees: float) -> str:
        """Map a heading in degrees (0–360) to an 8-point compass label."""
        deg = degrees % 360.0
        for upper_bound, label in _COMPASS_POINTS:
            if deg < upper_bound:
                return label
        # 337.5° – 360° wraps back to north.
        return "north"

    @staticmethod
    def _distance_between(
        lat1: float, lon1: float, lat2: float, lon2: float,
    ) -> float:
        """Great-circle distance via the Haversine formula (metres)."""
        lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
        lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)

        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r

        a = (
            math.sin(dlat / 2.0) ** 2
            + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2.0) ** 2
        )
        return _EARTH_RADIUS_M * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _heading_text(compass: str) -> str:
        return f"Facing {compass}"

    @staticmethod
    def _round_distance(metres: float) -> str:
        """Produce a speech-friendly distance string.

        Examples: "3 metres", "about 20 metres", "less than 1 metre".
        """
        if metres < 1.0:
            return "less than 1 metre"
        if metres < 10.0:
            return f"{metres:.0f} metres"
        # Round to nearest 5 for larger distances.
        rounded = int(round(metres / 5.0) * 5)
        return f"about {rounded} metres"
