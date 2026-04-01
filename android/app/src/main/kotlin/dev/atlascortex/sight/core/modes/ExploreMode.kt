package dev.atlascortex.sight.core.modes

import dev.atlascortex.sight.core.*

/**
 * Explore mode: continuous scene narration every ~500ms.
 * Obstacle alerts always pass through, descriptions are deduped.
 */
class ExploreMode(
    private val config: Config,
    private val obstacleWarner: ObstacleWarner,
    private val contextTracker: ContextTracker,
) {
    companion object {
        const val NARRATION_INTERVAL_MS = 500L
    }

    /** Build a spoken description for a scene. Returns null if too similar to last. */
    fun processScene(scene: SceneDescription): String? {
        if (!contextTracker.isNovel(scene.text)) return null
        return formatDescription(scene)
    }

    /** Always process obstacle alerts — safety first. */
    fun processObstacles(objects: List<DetectedObject>): List<String> {
        val obstacles = obstacleWarner.classifyObstacles(objects)
        return obstacles
            .filter { it.severity != ObstacleSeverity.INFO }
            .map { obstacleWarner.formatWarning(it) }
    }

    private fun formatDescription(scene: SceneDescription): String = when (config.verbosity.value) {
        Verbosity.BRIEF -> scene.text.split(".").firstOrNull()?.trim()?.plus(".") ?: scene.text
        Verbosity.NORMAL -> scene.text
        Verbosity.DETAILED -> buildDetailedDescription(scene)
    }

    private fun buildDetailedDescription(scene: SceneDescription): String {
        val sb = StringBuilder(scene.text)
        if (scene.objects.isNotEmpty()) {
            sb.append(" I can see ")
            sb.append(scene.objects.joinToString(", ") { obj ->
                val dist = obj.estimatedDistance?.let { " about ${String.format("%.1f", it)} meters away" } ?: ""
                "${obj.label}$dist"
            })
            sb.append(".")
        }
        return sb.toString()
    }
}
