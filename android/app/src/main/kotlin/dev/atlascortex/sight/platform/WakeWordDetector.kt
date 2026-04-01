package dev.atlascortex.sight.platform

import android.content.Context

/**
 * Wake word detector — "Hey Atlas" / "Atlas" keyword spotting.
 * Works by checking STT transcriptions from SpeechRecognizer for wake words.
 * No separate audio capture needed — piggybacks on the recognizer's mic stream.
 */
class WakeWordDetector(private val context: Context) {

    companion object {
        private val WAKE_WORDS = listOf("hey atlas", "atlas")
    }

    fun isReady(): Boolean = true

    suspend fun initialize(): Boolean = true

    /** Check transcribed text for wake words. */
    fun checkTranscription(text: String): Boolean {
        val lower = text.lowercase().trim()
        return WAKE_WORDS.any { lower.startsWith(it) || lower.contains(it) }
    }

    /** Strip the wake word from transcribed text to get the command. */
    fun stripWakeWord(text: String): String {
        var result = text.trim()
        for (word in WAKE_WORDS.sortedByDescending { it.length }) {
            val regex = Regex("(?i)^\\s*$word[,.]?\\s*")
            result = result.replace(regex, "")
        }
        return result.trim()
    }

    fun shutdown() { /* No resources to release */ }
}
