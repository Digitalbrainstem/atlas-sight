"""Tests for atlas_sight.data.models."""
from __future__ import annotations

from atlas_sight.data.models import (
    BoundingBox,
    DetectedObject,
    Gesture,
    GestureType,
    HistoryEntry,
    NavPoint,
    ObjectCategory,
    Obstacle,
    Orientation,
    Scene,
    Severity,
    TextBlock,
    VoiceCommand,
)


# ---------------------------------------------------------------------------
# BoundingBox
# ---------------------------------------------------------------------------


class TestBoundingBox:
    def test_center(self):
        bb = BoundingBox(0.0, 0.0, 1.0, 1.0)
        assert bb.center == (0.5, 0.5)

    def test_center_offset(self):
        bb = BoundingBox(0.2, 0.3, 0.8, 0.9)
        cx, cy = bb.center
        assert abs(cx - 0.5) < 1e-9
        assert abs(cy - 0.6) < 1e-9

    def test_area(self):
        bb = BoundingBox(0.0, 0.0, 0.5, 0.5)
        assert abs(bb.area - 0.25) < 1e-9

    def test_area_full_frame(self):
        bb = BoundingBox(0.0, 0.0, 1.0, 1.0)
        assert abs(bb.area - 1.0) < 1e-9

    def test_area_zero_when_inverted(self):
        bb = BoundingBox(0.5, 0.5, 0.1, 0.1)
        assert bb.area == 0.0

    def test_width_and_height(self):
        bb = BoundingBox(0.1, 0.2, 0.6, 0.9)
        assert abs(bb.width - 0.5) < 1e-9
        assert abs(bb.height - 0.7) < 1e-9

    def test_width_height_zero_when_inverted(self):
        bb = BoundingBox(0.8, 0.8, 0.2, 0.2)
        assert bb.width == 0.0
        assert bb.height == 0.0


# ---------------------------------------------------------------------------
# DetectedObject
# ---------------------------------------------------------------------------


class TestDetectedObject:
    def _make(self, category: ObjectCategory = ObjectCategory.OTHER) -> DetectedObject:
        return DetectedObject(
            label="thing",
            confidence=0.9,
            bbox=BoundingBox(0.0, 0.0, 0.5, 0.5),
            category=category,
        )

    def test_is_obstacle_for_obstacle_category(self):
        assert self._make(ObjectCategory.OBSTACLE).is_obstacle is True

    def test_is_obstacle_for_vehicle(self):
        assert self._make(ObjectCategory.VEHICLE).is_obstacle is True

    def test_is_obstacle_for_furniture(self):
        assert self._make(ObjectCategory.FURNITURE).is_obstacle is True

    def test_is_obstacle_for_stairs(self):
        assert self._make(ObjectCategory.STAIRS).is_obstacle is True

    def test_is_not_obstacle_for_person(self):
        assert self._make(ObjectCategory.PERSON).is_obstacle is False

    def test_is_not_obstacle_for_other(self):
        assert self._make(ObjectCategory.OTHER).is_obstacle is False

    def test_is_not_obstacle_for_sign(self):
        assert self._make(ObjectCategory.SIGN).is_obstacle is False

    def test_defaults(self):
        obj = DetectedObject(
            label="test",
            confidence=0.5,
            bbox=BoundingBox(0.0, 0.0, 1.0, 1.0),
        )
        assert obj.category == ObjectCategory.OTHER
        assert obj.distance_m is None
        assert obj.metadata == {}


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


class TestScene:
    def test_has_text_true(self):
        scene = Scene(
            description="test",
            text_blocks=[TextBlock(text="hello", confidence=0.9)],
        )
        assert scene.has_text is True

    def test_has_text_false(self):
        scene = Scene(description="test")
        assert scene.has_text is False

    def test_has_obstacles_true(self):
        scene = Scene(
            description="test",
            obstacles=[Obstacle(label="chair", distance_m=1.0, direction="left")],
        )
        assert scene.has_obstacles is True

    def test_has_obstacles_false(self):
        scene = Scene(description="test")
        assert scene.has_obstacles is False

    def test_danger_count(self):
        scene = Scene(
            description="test",
            obstacles=[
                Obstacle(label="car", distance_m=0.5, direction="center", severity=Severity.DANGER),
                Obstacle(label="chair", distance_m=1.5, direction="left", severity=Severity.WARNING),
                Obstacle(label="pole", distance_m=0.3, direction="right", severity=Severity.DANGER),
            ],
        )
        assert scene.danger_count == 2

    def test_danger_count_zero(self):
        scene = Scene(
            description="test",
            obstacles=[
                Obstacle(label="chair", distance_m=1.5, direction="left", severity=Severity.WARNING),
            ],
        )
        assert scene.danger_count == 0

    def test_defaults(self):
        scene = Scene(description="empty scene")
        assert scene.objects == []
        assert scene.text_blocks == []
        assert scene.obstacles == []
        assert scene.detail_level == "normal"
        assert scene.raw_image is None
        assert scene.timestamp > 0


# ---------------------------------------------------------------------------
# Obstacle
# ---------------------------------------------------------------------------


class TestObstacle:
    def test_is_dangerous_true(self):
        obs = Obstacle(label="car", distance_m=0.5, direction="center", severity=Severity.DANGER)
        assert obs.is_dangerous is True

    def test_is_dangerous_false_warning(self):
        obs = Obstacle(label="chair", distance_m=1.5, direction="left", severity=Severity.WARNING)
        assert obs.is_dangerous is False

    def test_is_dangerous_false_info(self):
        obs = Obstacle(label="sign", distance_m=5.0, direction="right", severity=Severity.INFO)
        assert obs.is_dangerous is False


# ---------------------------------------------------------------------------
# Orientation
# ---------------------------------------------------------------------------


class TestOrientation:
    def test_has_location_true(self):
        o = Orientation(latitude=37.7749, longitude=-122.4194)
        assert o.has_location is True

    def test_has_location_false_no_lat(self):
        o = Orientation(longitude=-122.4194)
        assert o.has_location is False

    def test_has_location_false_no_lon(self):
        o = Orientation(latitude=37.7749)
        assert o.has_location is False

    def test_has_location_false_default(self):
        o = Orientation()
        assert o.has_location is False

    def test_defaults(self):
        o = Orientation()
        assert o.heading_degrees is None
        assert o.altitude_m is None
        assert o.accuracy_m is None


# ---------------------------------------------------------------------------
# Simple model creation
# ---------------------------------------------------------------------------


class TestModelCreation:
    def test_navpoint_defaults(self):
        np_ = NavPoint(name="home", latitude=0.0, longitude=0.0)
        assert np_.description == ""
        assert np_.timestamp > 0

    def test_gesture_defaults(self):
        g = Gesture(gesture_type=GestureType.DOUBLE_TAP)
        assert g.metadata == {}
        assert g.timestamp > 0

    def test_voice_command_defaults(self):
        vc = VoiceCommand(raw_text="hello", intent="describe")
        assert vc.confidence == 1.0
        assert vc.parameters == {}
        assert vc.timestamp > 0

    def test_history_entry_defaults(self):
        scene = Scene(description="test")
        he = HistoryEntry(scene=scene, spoken_text="test description")
        assert he.mode == "explore"
        assert he.bookmarked is False
        assert he.timestamp > 0

    def test_text_block_defaults(self):
        tb = TextBlock(text="hello", confidence=0.9)
        assert tb.bbox is None
        assert tb.language == "en"
