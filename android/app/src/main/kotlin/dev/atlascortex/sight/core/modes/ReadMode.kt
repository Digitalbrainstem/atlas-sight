package dev.atlascortex.sight.core.modes

import dev.atlascortex.sight.core.*

/**
 * Read mode: OCR text reading in natural order (top-to-bottom, left-to-right).
 */
class ReadMode(
    private val config: Config,
) {
    /** Format raw OCR text for natural spoken reading. */
    fun processText(rawText: String): String? {
        val cleaned = cleanOcrText(rawText)
        if (cleaned.isBlank()) return null
        return when (config.verbosity.value) {
            Verbosity.BRIEF -> {
                val lines = cleaned.lines().take(3)
                lines.joinToString(". ")
            }
            Verbosity.NORMAL -> cleaned
            Verbosity.DETAILED -> "I can read the following text: $cleaned"
        }
    }

    /** Announce when no text is found. */
    fun noTextFound(): String = "No readable text detected. Try pointing the camera at text."

    private fun cleanOcrText(text: String): String =
        text.lines()
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .joinToString("\n")
}
