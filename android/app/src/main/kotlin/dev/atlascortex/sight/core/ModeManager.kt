package dev.atlascortex.sight.core

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * 4-mode state machine — EXPLORE, READ, NAVIGATE, IDENTIFY.
 * Dispatches frame processing and commands to the active mode.
 */
class ModeManager(
    private val config: Config,
    private val contextTracker: ContextTracker,
) {
    private val _currentMode = MutableStateFlow(SightMode.EXPLORE)
    val currentMode: StateFlow<SightMode> = _currentMode.asStateFlow()

    /** Callbacks set by SightEngine after construction. */
    var onModeChanged: ((SightMode, SightMode) -> Unit)? = null

    fun switchMode(newMode: SightMode) {
        val oldMode = _currentMode.value
        if (oldMode == newMode) return
        contextTracker.reset()
        _currentMode.value = newMode
        onModeChanged?.invoke(oldMode, newMode)
    }

    /** Map a voice intent to a mode switch (if applicable). Returns true if handled. */
    fun handleIntent(intent: VoiceIntent): Boolean = when (intent) {
        VoiceIntent.DESCRIBE -> { switchMode(SightMode.EXPLORE); true }
        VoiceIntent.READ_TEXT -> { switchMode(SightMode.READ); true }
        VoiceIntent.NAVIGATE -> { switchMode(SightMode.NAVIGATE); true }
        VoiceIntent.IDENTIFY -> { switchMode(SightMode.IDENTIFY); true }
        VoiceIntent.CHECK_AHEAD -> { switchMode(SightMode.NAVIGATE); true }
        else -> false
    }
}
