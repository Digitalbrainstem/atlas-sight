package dev.atlascortex.sight.core

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** User-facing configuration — speech speed, volume, verbosity. */
class Config {
    private val _speechSpeed = MutableStateFlow(1.0f)
    val speechSpeed: StateFlow<Float> = _speechSpeed.asStateFlow()

    private val _volume = MutableStateFlow(1.0f)
    val volume: StateFlow<Float> = _volume.asStateFlow()

    private val _verbosity = MutableStateFlow(Verbosity.NORMAL)
    val verbosity: StateFlow<Verbosity> = _verbosity.asStateFlow()

    private val _continuousMode = MutableStateFlow(true)
    val continuousMode: StateFlow<Boolean> = _continuousMode.asStateFlow()

    fun adjustSpeed(delta: Float) {
        _speechSpeed.value = (_speechSpeed.value + delta).coerceIn(0.5f, 3.0f)
    }

    fun setSpeed(speed: Float) {
        _speechSpeed.value = speed.coerceIn(0.5f, 3.0f)
    }

    fun adjustVolume(delta: Float) {
        _volume.value = (_volume.value + delta).coerceIn(0.1f, 1.0f)
    }

    fun cycleVerbosity(): Verbosity {
        _verbosity.value = when (_verbosity.value) {
            Verbosity.BRIEF -> Verbosity.NORMAL
            Verbosity.NORMAL -> Verbosity.DETAILED
            Verbosity.DETAILED -> Verbosity.BRIEF
        }
        return _verbosity.value
    }

    fun toggleContinuousMode(): Boolean {
        _continuousMode.value = !_continuousMode.value
        return _continuousMode.value
    }

    fun getSpeedForProfile(profile: SpeedProfile): Float = when (profile) {
        SpeedProfile.NAVIGATION -> 1.0f
        SpeedProfile.ALERT -> 0.85f
        SpeedProfile.GENERAL -> _speechSpeed.value
    }
}
