"""Tests for atlas_sight.navigation (orientation + obstacle)."""
from __future__ import annotations

import math

import pytest

from atlas_sight.config import NavigationSettings
from atlas_sight.data.models import (
    BoundingBox,
    DetectedObject,
    ObjectCategory,
    Obstacle,
    Severity,
)
from atlas_sight.navigation.obstacle import (
    ObstacleWarner,
    _direction_text,
    _distance_text,
    _severity_prefix,
)
from atlas_sight.navigation.orientation import OrientationHelper


# ===========================================================================
# OrientationHelper
# ===========================================================================


class TestHeadingToCompass:
    @pytest.fixture()
    def helper(self) -> OrientationHelper:
        return OrientationHelper(NavigationSettings())

    @pytest.mark.parametrize(
        "degrees,expected",
        [
            (0.0, "north"),
            (10.0, "north"),
            (45.0, "north-east"),
            (90.0, "east"),
            (135.0, "south-east"),
            (180.0, "south"),
            (225.0, "south-west"),
            (270.0, "west"),
            (315.0, "north-west"),
            (350.0, "north"),
            (360.0, "north"),
        ],
    )
    def test_compass_directions(self, helper: OrientationHelper, degrees: float, expected: str):
        assert helper._heading_to_compass(degrees) == expected

    def test_wrap_around(self, helper: OrientationHelper):
        assert helper._heading_to_compass(720.0) == "north"

    def test_negative_degrees(self, helper: OrientationHelper):
        # -90 % 360 = 270 → west
        assert helper._heading_to_compass(-90.0) == "west"


class TestHaversineDistance:
    @pytest.fixture()
    def helper(self) -> OrientationHelper:
        return OrientationHelper(NavigationSettings())

    def test_same_point_is_zero(self, helper: OrientationHelper):
        d = helper._distance_between(37.0, -122.0, 37.0, -122.0)
        assert abs(d) < 1e-6

    def test_known_distance(self, helper: OrientationHelper):
        # Approximate distance NYC → LA: ~3944 km
        d = helper._distance_between(40.7128, -74.0060, 34.0522, -118.2437)
        assert 3_900_000 < d < 4_000_000

    def test_short_distance(self, helper: OrientationHelper):
        # ~111 km for 1 degree latitude at equator
        d = helper._distance_between(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < d < 112_000


class TestOrientationHelperAsync:
    async def test_get_orientation(self):
        helper = OrientationHelper(NavigationSettings())
        o = await helper.get_orientation()
        assert o is not None

    async def test_get_heading_description(self):
        helper = OrientationHelper(NavigationSettings())
        desc = await helper.get_heading_description()
        assert "facing" in desc.lower()

    async def test_save_landmark(self):
        helper = OrientationHelper(NavigationSettings())
        # Set a location
        helper._current.latitude = 37.7749
        helper._current.longitude = -122.4194
        point = await helper.save_landmark("office")
        assert point.name == "office"

    async def test_save_landmark_no_gps_raises(self):
        helper = OrientationHelper(NavigationSettings())
        helper._current.latitude = None
        helper._current.longitude = None
        with pytest.raises(RuntimeError, match="no GPS"):
            await helper.save_landmark("test")

    async def test_get_nearest_landmark(self):
        helper = OrientationHelper(NavigationSettings())
        helper._current.latitude = 37.7749
        helper._current.longitude = -122.4194
        await helper.save_landmark("nearby")
        result = await helper.get_nearest_landmark()
        assert result is not None
        landmark, distance = result
        assert landmark.name == "nearby"
        assert distance < 1.0  # Same location

    async def test_get_nearest_landmark_no_landmarks(self):
        helper = OrientationHelper(NavigationSettings())
        helper._current.latitude = 37.0
        helper._current.longitude = -122.0
        result = await helper.get_nearest_landmark()
        assert result is None


class TestRoundDistance:
    @pytest.fixture()
    def helper(self) -> OrientationHelper:
        return OrientationHelper(NavigationSettings())

    def test_less_than_one(self, helper: OrientationHelper):
        assert helper._round_distance(0.5) == "less than 1 metre"

    def test_under_ten(self, helper: OrientationHelper):
        assert helper._round_distance(3.0) == "3 metres"

    def test_larger_rounds_to_five(self, helper: OrientationHelper):
        result = helper._round_distance(22.0)
        assert "about" in result


# ===========================================================================
# ObstacleWarner
# ===========================================================================


class TestObstacleWarner:
    @pytest.fixture()
    def warner(self) -> ObstacleWarner:
        return ObstacleWarner(NavigationSettings())

    def _make_obj(
        self,
        label: str = "chair",
        category: ObjectCategory = ObjectCategory.FURNITURE,
        bbox: BoundingBox | None = None,
        distance_m: float | None = None,
    ) -> DetectedObject:
        return DetectedObject(
            label=label,
            confidence=0.9,
            bbox=bbox or BoundingBox(0.3, 0.3, 0.7, 0.7),
            category=category,
            distance_m=distance_m,
        )


class TestEstimateDistance:
    def test_uses_explicit_distance(self):
        warner = ObstacleWarner(NavigationSettings())
        obj = DetectedObject(
            label="car",
            confidence=0.9,
            bbox=BoundingBox(0.0, 0.0, 0.5, 0.5),
            category=ObjectCategory.VEHICLE,
            distance_m=2.5,
        )
        d = warner._estimate_distance(obj)
        assert d == 2.5

    def test_heuristic_large_bbox_close(self):
        warner = ObstacleWarner(NavigationSettings())
        obj = DetectedObject(
            label="chair",
            confidence=0.9,
            bbox=BoundingBox(0.0, 0.0, 1.0, 1.0),
            category=ObjectCategory.FURNITURE,
        )
        d = warner._estimate_distance(obj)
        assert d < 1.0

    def test_heuristic_small_bbox_far(self):
        warner = ObstacleWarner(NavigationSettings())
        obj = DetectedObject(
            label="sign",
            confidence=0.9,
            bbox=BoundingBox(0.45, 0.45, 0.55, 0.55),
            category=ObjectCategory.OBSTACLE,
        )
        d = warner._estimate_distance(obj)
        assert d > 3.0


class TestClassifyDirection:
    def test_left(self):
        warner = ObstacleWarner(NavigationSettings())
        bb = BoundingBox(0.0, 0.0, 0.2, 1.0)
        assert warner._classify_direction(bb) == "left"

    def test_center(self):
        warner = ObstacleWarner(NavigationSettings())
        bb = BoundingBox(0.35, 0.0, 0.65, 1.0)
        assert warner._classify_direction(bb) == "center"

    def test_right(self):
        warner = ObstacleWarner(NavigationSettings())
        bb = BoundingBox(0.8, 0.0, 1.0, 1.0)
        assert warner._classify_direction(bb) == "right"


class TestAssignSeverity:
    def test_danger(self):
        warner = ObstacleWarner(NavigationSettings(obstacle_danger_distance_m=0.8))
        assert warner._assign_severity(0.5) == Severity.DANGER

    def test_warning(self):
        warner = ObstacleWarner(NavigationSettings(
            obstacle_danger_distance_m=0.8,
            obstacle_warn_distance_m=2.0,
        ))
        assert warner._assign_severity(1.5) == Severity.WARNING

    def test_info(self):
        warner = ObstacleWarner(NavigationSettings(obstacle_warn_distance_m=2.0))
        assert warner._assign_severity(5.0) == Severity.INFO


class TestAnalyze:
    async def test_empty_objects(self):
        warner = ObstacleWarner(NavigationSettings())
        obstacles = await warner.analyze([])
        assert obstacles == []

    async def test_non_obstacle_filtered(self):
        warner = ObstacleWarner(NavigationSettings())
        obj = DetectedObject(
            label="person",
            confidence=0.9,
            bbox=BoundingBox(0.3, 0.3, 0.7, 0.7),
            category=ObjectCategory.PERSON,
        )
        obstacles = await warner.analyze([obj])
        assert obstacles == []

    async def test_obstacle_included(self):
        warner = ObstacleWarner(NavigationSettings())
        obj = DetectedObject(
            label="chair",
            confidence=0.9,
            bbox=BoundingBox(0.3, 0.3, 0.7, 0.7),
            category=ObjectCategory.FURNITURE,
            distance_m=1.0,
        )
        obstacles = await warner.analyze([obj])
        assert len(obstacles) == 1
        assert obstacles[0].label == "chair"


class TestWarningMessage:
    async def test_none_for_empty(self):
        warner = ObstacleWarner(NavigationSettings())
        msg = await warner.get_warning_message([])
        assert msg is None

    async def test_none_for_info_only(self):
        warner = ObstacleWarner(NavigationSettings())
        obs = [Obstacle(label="sign", distance_m=5.0, direction="right", severity=Severity.INFO)]
        msg = await warner.get_warning_message(obs)
        assert msg is None

    async def test_single_warning(self):
        warner = ObstacleWarner(NavigationSettings())
        obs = [Obstacle(label="chair", distance_m=1.5, direction="left", severity=Severity.WARNING)]
        msg = await warner.get_warning_message(obs)
        assert msg is not None
        assert "chair" in msg.lower()

    async def test_danger_message(self):
        warner = ObstacleWarner(NavigationSettings())
        obs = [Obstacle(label="stairs", distance_m=0.5, direction="center", severity=Severity.DANGER)]
        msg = await warner.get_warning_message(obs)
        assert "stop" in msg.lower()

    async def test_multiple_obstacles(self):
        warner = ObstacleWarner(NavigationSettings())
        obs = [
            Obstacle(label="car", distance_m=0.5, direction="center", severity=Severity.DANGER),
            Obstacle(label="chair", distance_m=1.5, direction="left", severity=Severity.WARNING),
        ]
        msg = await warner.get_warning_message(obs)
        assert msg is not None
        assert "and" in msg


class TestFormatHelpers:
    def test_distance_text_close(self):
        assert "less than 1 metre" in _distance_text(0.5)

    def test_distance_text_far(self):
        result = _distance_text(3.0)
        assert "about 3 metres" in result

    def test_direction_text_center(self):
        assert _direction_text("center") == ""

    def test_direction_text_left(self):
        assert "left" in _direction_text("left")

    def test_severity_prefix_danger(self):
        assert _severity_prefix(Severity.DANGER) == "Stop! "

    def test_severity_prefix_warning(self):
        assert _severity_prefix(Severity.WARNING) == "Caution: "

    def test_severity_prefix_info(self):
        assert _severity_prefix(Severity.INFO) == ""
