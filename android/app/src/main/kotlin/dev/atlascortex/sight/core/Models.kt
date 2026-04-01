package dev.atlascortex.sight.core

/** All shared data types for Atlas Sight. */

enum class SightMode(val label: String) {
    EXPLORE("Explore"),
    READ("Read"),
    NAVIGATE("Navigate"),
    IDENTIFY("Identify")
}

enum class VoiceIntent {
    DESCRIBE, READ_TEXT, LOCATE, CHECK_AHEAD, IDENTIFY, NAVIGATE,
    FASTER, SLOWER, LOUDER, SOFTER, MORE_DETAIL, LESS_DETAIL,
    REMEMBER, REPEAT, STOP, NORMAL_SPEED, MAX_SPEED,
    UNKNOWN
}

enum class Verbosity { BRIEF, NORMAL, DETAILED }

enum class ObjectCategory {
    PERSON, VEHICLE, FURNITURE, DOOR, STAIRS, OBSTACLE,
    SIGN, ANIMAL, FOOD, ELECTRONIC, OTHER
}

enum class ObstacleSeverity { INFO, WARNING, DANGER }

enum class HapticPattern { ACKNOWLEDGE, SUCCESS, WARNING, DANGER, HEARTBEAT, NAVIGATE }

enum class AudioCueType { BEEP, CHIME, WARNING, DANGER, RISING, FALLING, MODE_SWITCH }

enum class SpeedProfile { NAVIGATION, ALERT, GENERAL }

data class BoundingBox(
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
) {
    val width: Float get() = right - left
    val height: Float get() = bottom - top
    val area: Float get() = width * height
    val centerX: Float get() = (left + right) / 2f
    val centerY: Float get() = (top + bottom) / 2f
}

data class DetectedObject(
    val label: String,
    val category: ObjectCategory,
    val confidence: Float,
    val boundingBox: BoundingBox? = null,
    val estimatedDistance: Float? = null,
)

data class SceneDescription(
    val text: String,
    val objects: List<DetectedObject> = emptyList(),
    val verbosity: Verbosity = Verbosity.NORMAL,
    val timestamp: Long = System.currentTimeMillis(),
)

data class Obstacle(
    val obj: DetectedObject,
    val severity: ObstacleSeverity,
    val direction: String,
    val distance: Float,
)

data class Landmark(
    val name: String,
    val latitude: Double,
    val longitude: Double,
    val timestamp: Long = System.currentTimeMillis(),
)

data class SpeechItem(
    val text: String,
    val priority: Int,
    val speedProfile: SpeedProfile = SpeedProfile.GENERAL,
    val sequence: Long = sequenceCounter++,
) : Comparable<SpeechItem> {
    override fun compareTo(other: SpeechItem): Int {
        val p = priority.compareTo(other.priority)
        return if (p != 0) p else sequence.compareTo(other.sequence)
    }

    companion object {
        @Volatile
        private var sequenceCounter: Long = 0L
    }
}

data class CommandMatch(
    val intent: VoiceIntent,
    val confidence: Float,
    val extras: Map<String, String> = emptyMap(),
)
