"""Core data models for Atlas Sight."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ObjectCategory(Enum):
    """Broad categories for detected objects."""
    PERSON = "person"
    VEHICLE = "vehicle"
    FURNITURE = "furniture"
    DOOR = "door"
    STAIRS = "stairs"
    OBSTACLE = "obstacle"
    SIGN = "sign"
    ANIMAL = "animal"
    FOOD = "food"
    ELECTRONIC = "electronic"
    OTHER = "other"


class Severity(Enum):
    """Severity levels for obstacles and alerts."""
    INFO = "info"
    WARNING = "warning"
    DANGER = "danger"


class GestureType(Enum):
    """Supported gesture types."""
    DOUBLE_TAP = "double_tap"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_LEFT = "swipe_left"
    SWIPE_UP = "swipe_up"
    SWIPE_DOWN = "swipe_down"
    SHAKE = "shake"
    LONG_PRESS = "long_press"
    TWO_FINGER_TAP = "two_finger_tap"


# ---------------------------------------------------------------------------
# Vision data
# ---------------------------------------------------------------------------

@dataclass
class BoundingBox:
    """Bounding box in normalised coordinates (0.0–1.0)."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2

    @property
    def area(self) -> float:
        return max(0.0, self.x_max - self.x_min) * max(0.0, self.y_max - self.y_min)

    @property
    def width(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return max(0.0, self.y_max - self.y_min)


@dataclass
class DetectedObject:
    """A single detected object in a frame."""
    label: str
    confidence: float
    bbox: BoundingBox
    category: ObjectCategory = ObjectCategory.OTHER
    distance_m: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_obstacle(self) -> bool:
        return self.category in {
            ObjectCategory.OBSTACLE,
            ObjectCategory.VEHICLE,
            ObjectCategory.FURNITURE,
            ObjectCategory.STAIRS,
        }


@dataclass
class TextBlock:
    """A block of text detected via OCR."""
    text: str
    confidence: float
    bbox: BoundingBox | None = None
    language: str = "en"


@dataclass
class Obstacle:
    """An obstacle detected in the user's path."""
    label: str
    distance_m: float
    direction: str  # "left", "center", "right"
    severity: Severity = Severity.INFO
    bbox: BoundingBox | None = None

    @property
    def is_dangerous(self) -> bool:
        return self.severity == Severity.DANGER


# ---------------------------------------------------------------------------
# Scene data
# ---------------------------------------------------------------------------

@dataclass
class Scene:
    """A complete snapshot of what the camera sees right now."""
    description: str
    objects: list[DetectedObject] = field(default_factory=list)
    text_blocks: list[TextBlock] = field(default_factory=list)
    obstacles: list[Obstacle] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    detail_level: str = "normal"
    raw_image: bytes | None = field(default=None, repr=False)

    @property
    def has_text(self) -> bool:
        return len(self.text_blocks) > 0

    @property
    def has_obstacles(self) -> bool:
        return len(self.obstacles) > 0

    @property
    def danger_count(self) -> int:
        return sum(1 for o in self.obstacles if o.is_dangerous)


# ---------------------------------------------------------------------------
# Navigation data
# ---------------------------------------------------------------------------

@dataclass
class NavPoint:
    """A saved navigation landmark."""
    name: str
    latitude: float
    longitude: float
    description: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class Orientation:
    """Current device orientation and location."""
    heading_degrees: float | None = None  # compass bearing
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    accuracy_m: float | None = None

    @property
    def has_location(self) -> bool:
        return self.latitude is not None and self.longitude is not None


# ---------------------------------------------------------------------------
# Interaction data
# ---------------------------------------------------------------------------

@dataclass
class Gesture:
    """A gesture event from the touch/motion sensors."""
    gesture_type: GestureType
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VoiceCommand:
    """A parsed voice command."""
    raw_text: str
    intent: str  # normalised command name
    confidence: float = 1.0
    parameters: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# History data
# ---------------------------------------------------------------------------

@dataclass
class HistoryEntry:
    """A single entry in the session history."""
    scene: Scene
    spoken_text: str
    mode: str = "explore"
    bookmarked: bool = False
    timestamp: float = field(default_factory=time.time)
