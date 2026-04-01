package dev.atlascortex.sight.core

import kotlin.math.abs

/**
 * Jaccard word-overlap similarity to prevent repetitive scene descriptions.
 * If the new description is too similar to the last spoken one, skip it.
 */
class ContextTracker {
    private var lastWords: Set<String> = emptySet()
    private var lastText: String = ""
    private val similarityThreshold = 0.6f

    /** Returns true if the new text is novel enough to speak. */
    fun isNovel(text: String): Boolean {
        val words = tokenize(text)
        if (lastWords.isEmpty()) {
            update(text, words)
            return true
        }
        val similarity = jaccardSimilarity(lastWords, words)
        return if (similarity < similarityThreshold) {
            update(text, words)
            true
        } else {
            false
        }
    }

    /** Force-update context (used after mode switches). */
    fun reset() {
        lastWords = emptySet()
        lastText = ""
    }

    fun getLastText(): String = lastText

    private fun update(text: String, words: Set<String>) {
        lastText = text
        lastWords = words
    }

    private fun tokenize(text: String): Set<String> =
        text.lowercase()
            .replace(Regex("[^a-z0-9\\s]"), "")
            .split(Regex("\\s+"))
            .filter { it.length > 2 }
            .toSet()

    private fun jaccardSimilarity(a: Set<String>, b: Set<String>): Float {
        if (a.isEmpty() && b.isEmpty()) return 1.0f
        val intersection = a.intersect(b).size
        val union = a.union(b).size
        return if (union == 0) 0f else intersection.toFloat() / union.toFloat()
    }
}
