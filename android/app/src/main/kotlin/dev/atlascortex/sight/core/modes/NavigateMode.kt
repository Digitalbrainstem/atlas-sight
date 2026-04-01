package dev.atlascortex.sight.core.modes

import dev.atlascortex.sight.core.*

/**
 * Navigate mode: continuous obstacle scanning every ~1s with
 * escalating severity warnings and compass heading.
 */
class NavigateMode(
    private val obstacleWarner: ObstacleWarner,
    private val orientationHelper: OrientationHelper,
) {
    companion object {
        const val SCAN_INTERVAL_MS = 1000L
    }

    private var lastWarnedObstacles = mutableMapOf<String, Long>()

    /** Process a frame for obstacle warnings. Returns spoken warnings. */
    fun processObstacles(objects: List<DetectedObject>): List<NavigationAlert> {
        val obstacles = obstacleWarner.classifyObstacles(objects)
        val now = System.currentTimeMillis()
        val alerts = mutableListOf<NavigationAlert>()

        for (obstacle in obstacles) {
            val key = "${obstacle.obj.category}_${obstacle.direction}"
            val lastWarned = lastWarnedObstacles[key] ?: 0L

            // Escalate: DANGER always warns, WARNING every 3s, INFO every 10s
            val cooldown = when (obstacle.severity) {
                ObstacleSeverity.DANGER -> 0L
                ObstacleSeverity.WARNING -> 3000L
                ObstacleSeverity.INFO -> 10000L
            }

            if (now - lastWarned >= cooldown) {
                lastWarnedObstacles[key] = now
                alerts.add(
                    NavigationAlert(
                        text = obstacleWarner.formatWarning(obstacle),
                        severity = obstacle.severity,
                        haptic = when (obstacle.severity) {
                            ObstacleSeverity.DANGER -> HapticPattern.DANGER
                            ObstacleSeverity.WARNING -> HapticPattern.WARNING
                            else -> null
                        },
                        audioCue = when (obstacle.severity) {
                            ObstacleSeverity.DANGER -> AudioCueType.DANGER
                            ObstacleSeverity.WARNING -> AudioCueType.WARNING
                            else -> null
                        },
                    )
                )
            }
        }
        return alerts
    }

    /** Periodic compass heading announcement. */
    fun getHeadingAnnouncement(): String {
        val direction = orientationHelper.getCompassDirection()
        return "Heading $direction."
    }

    fun reset() {
        lastWarnedObstacles.clear()
    }

    data class NavigationAlert(
        val text: String,
        val severity: ObstacleSeverity,
        val haptic: HapticPattern?,
        val audioCue: AudioCueType?,
    )
}
