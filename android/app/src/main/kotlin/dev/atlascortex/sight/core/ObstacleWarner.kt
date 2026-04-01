package dev.atlascortex.sight.core

/**
 * Obstacle severity classification and directional warnings.
 * DANGER (<0.8m), WARNING (<2.0m), INFO (>=2.0m).
 */
class ObstacleWarner {
    companion object {
        private const val DANGER_DISTANCE = 0.8f
        private const val WARNING_DISTANCE = 2.0f

        private val OBSTACLE_CATEGORIES = setOf(
            ObjectCategory.OBSTACLE,
            ObjectCategory.VEHICLE,
            ObjectCategory.FURNITURE,
            ObjectCategory.STAIRS,
        )
    }

    fun classifyObstacles(objects: List<DetectedObject>): List<Obstacle> =
        objects
            .filter { it.category in OBSTACLE_CATEGORIES || isBlockingPath(it) }
            .mapNotNull { obj ->
                val distance = obj.estimatedDistance ?: estimateDistance(obj) ?: return@mapNotNull null
                val severity = classifySeverity(distance)
                val direction = estimateDirection(obj)
                Obstacle(obj, severity, direction, distance)
            }
            .sortedBy { it.distance }

    fun classifySeverity(distance: Float): ObstacleSeverity = when {
        distance < DANGER_DISTANCE -> ObstacleSeverity.DANGER
        distance < WARNING_DISTANCE -> ObstacleSeverity.WARNING
        else -> ObstacleSeverity.INFO
    }

    /** Format a spoken warning for the given obstacle. */
    fun formatWarning(obstacle: Obstacle): String {
        val prefix = when (obstacle.severity) {
            ObstacleSeverity.DANGER -> "Danger!"
            ObstacleSeverity.WARNING -> "Warning."
            ObstacleSeverity.INFO -> ""
        }
        val dist = String.format("%.1f meters", obstacle.distance)
        return "$prefix ${obstacle.obj.label} ${obstacle.direction}, $dist away.".trim()
    }

    /** Distance estimation from bounding box area (normalized 0–1). */
    private fun estimateDistance(obj: DetectedObject): Float? {
        val bbox = obj.boundingBox ?: return null
        val area = bbox.area
        return when {
            area > 0.25f -> 0.8f   // Large object = close
            area > 0.05f -> 2.5f   // Medium
            else -> 5.0f           // Small = far
        }
    }

    /** Estimate direction from bounding box center position. */
    private fun estimateDirection(obj: DetectedObject): String {
        val bbox = obj.boundingBox ?: return "ahead"
        return when {
            bbox.centerX < 0.33f -> "to your left"
            bbox.centerX > 0.67f -> "to your right"
            else -> "ahead"
        }
    }

    /** Any large object in the center path is blocking. */
    private fun isBlockingPath(obj: DetectedObject): Boolean {
        val bbox = obj.boundingBox ?: return false
        return bbox.centerX in 0.2f..0.8f && bbox.area > 0.1f
    }
}
