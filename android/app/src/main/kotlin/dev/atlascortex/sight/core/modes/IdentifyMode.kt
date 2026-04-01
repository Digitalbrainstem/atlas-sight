package dev.atlascortex.sight.core.modes

import dev.atlascortex.sight.core.*

/**
 * Identify mode: point-and-ask single object identification.
 * Captures one frame, runs detailed VLM analysis, speaks result.
 */
class IdentifyMode(
    private val config: Config,
) {
    /** Format a single-object identification result for speech. */
    fun formatIdentification(scene: SceneDescription): String {
        if (scene.objects.isEmpty()) {
            return "I'm not sure what that is. Try moving the camera closer."
        }

        val primary = scene.objects.first()
        val base = when (config.verbosity.value) {
            Verbosity.BRIEF -> "That's ${addArticle(primary.label)}."
            Verbosity.NORMAL -> buildNormalDescription(primary, scene.text)
            Verbosity.DETAILED -> buildDetailedDescription(primary, scene)
        }
        return base
    }

    /** Follow-up Q&A about the identified object. */
    fun formatFollowUp(question: String, answer: String): String {
        return answer.ifBlank { "I'm not sure about that. Try asking a different question." }
    }

    private fun buildNormalDescription(obj: DetectedObject, sceneText: String): String {
        val distance = obj.estimatedDistance?.let {
            ", about ${String.format("%.1f", it)} meters away"
        } ?: ""
        return if (sceneText.isNotBlank()) {
            sceneText
        } else {
            "That appears to be ${addArticle(obj.label)}$distance."
        }
    }

    private fun buildDetailedDescription(obj: DetectedObject, scene: SceneDescription): String {
        val sb = StringBuilder()
        sb.append(scene.text.ifBlank { "I see ${addArticle(obj.label)}." })
        obj.estimatedDistance?.let {
            sb.append(" It's approximately ${String.format("%.1f", it)} meters away.")
        }
        obj.boundingBox?.let { bbox ->
            val position = when {
                bbox.centerX < 0.33f -> "on the left side"
                bbox.centerX > 0.67f -> "on the right side"
                else -> "in the center"
            }
            sb.append(" It's $position of your view.")
        }
        if (scene.objects.size > 1) {
            val others = scene.objects.drop(1).take(3)
            sb.append(" I also see ")
            sb.append(others.joinToString(", ") { it.label })
            sb.append(" nearby.")
        }
        return sb.toString()
    }

    private fun addArticle(label: String): String {
        val vowels = "aeiou"
        val article = if (label.first().lowercase()[0] in vowels) "an" else "a"
        return "$article $label"
    }
}
