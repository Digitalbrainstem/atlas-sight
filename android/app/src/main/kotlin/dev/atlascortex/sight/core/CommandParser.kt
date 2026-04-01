package dev.atlascortex.sight.core

/** Pattern-matching command parser — 25+ voice intents, no ML needed. */
class CommandParser {
    private data class IntentPattern(
        val regex: Regex,
        val intent: VoiceIntent,
    )

    private val patterns: List<IntentPattern> = listOf(
        // Scene description
        IntentPattern(
            Regex("(?i)(what do you see|what can you see|describe|what'?s around|look around|tell me what you see|scene|surroundings)"),
            VoiceIntent.DESCRIBE
        ),
        // Text reading
        IntentPattern(
            Regex("(?i)(read the|read this|read text|what does it say|what does that say|read sign|read menu|read label|read that)"),
            VoiceIntent.READ_TEXT
        ),
        // Location
        IntentPattern(
            Regex("(?i)(where am i|my location|where is this|what place)"),
            VoiceIntent.LOCATE
        ),
        // Safety check
        IntentPattern(
            Regex("(?i)(check ahead|any obstacle|is it safe|clear ahead|path clear|what'?s ahead|obstacles)"),
            VoiceIntent.CHECK_AHEAD
        ),
        // Identify
        IntentPattern(
            Regex("(?i)(what is this|what'?s this|identify|tell me about this|what am i (holding|looking|pointing))"),
            VoiceIntent.IDENTIFY
        ),
        // Navigate
        IntentPattern(
            Regex("(?i)(start navigat|guide me|navigat|help me walk|help me get)"),
            VoiceIntent.NAVIGATE
        ),
        // Speed — faster
        IntentPattern(Regex("(?i)\\bfaster\\b"), VoiceIntent.FASTER),
        // Speed — slower
        IntentPattern(Regex("(?i)\\bslower\\b"), VoiceIntent.SLOWER),
        // Speed — normal
        IntentPattern(
            Regex("(?i)(normal speed|default speed|reset speed|regular speed)"),
            VoiceIntent.NORMAL_SPEED
        ),
        // Speed — max
        IntentPattern(
            Regex("(?i)(max speed|maximum speed|fastest|full speed)"),
            VoiceIntent.MAX_SPEED
        ),
        // Volume — louder
        IntentPattern(
            Regex("(?i)(louder|volume up|speak up|turn up)"),
            VoiceIntent.LOUDER
        ),
        // Volume — softer
        IntentPattern(
            Regex("(?i)(softer|quieter|volume down|quiet|turn down)"),
            VoiceIntent.SOFTER
        ),
        // Detail — more
        IntentPattern(
            Regex("(?i)(more detail|elaborate|tell me more|explain more|go on)"),
            VoiceIntent.MORE_DETAIL
        ),
        // Detail — less
        IntentPattern(
            Regex("(?i)(less detail|be brief|brief|short|summarize|keep it short)"),
            VoiceIntent.LESS_DETAIL
        ),
        // Memory
        IntentPattern(
            Regex("(?i)(remember this|bookmark|save this|mark this)"),
            VoiceIntent.REMEMBER
        ),
        // Control — repeat
        IntentPattern(
            Regex("(?i)(\\brepeat\\b|say that again|what did you say|again)"),
            VoiceIntent.REPEAT
        ),
        // Control — stop
        IntentPattern(
            Regex("(?i)(\\bstop\\b|quiet|shut up|silence|cancel|pause|hush|enough)"),
            VoiceIntent.STOP
        ),
    )

    fun parse(text: String): CommandMatch {
        val normalized = text.trim()
        for (pattern in patterns) {
            if (pattern.regex.containsMatchIn(normalized)) {
                return CommandMatch(
                    intent = pattern.intent,
                    confidence = 0.9f,
                    extras = extractExtras(normalized, pattern.intent),
                )
            }
        }
        return CommandMatch(VoiceIntent.UNKNOWN, 0.0f)
    }

    private fun extractExtras(text: String, intent: VoiceIntent): Map<String, String> {
        if (intent == VoiceIntent.REMEMBER) {
            val match = Regex("(?i)remember this as (.+)").find(text)
            if (match != null) {
                return mapOf("label" to match.groupValues[1].trim())
            }
        }
        return emptyMap()
    }
}
