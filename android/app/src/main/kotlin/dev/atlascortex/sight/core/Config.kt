package dev.atlascortex.sight.core

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** User-facing configuration — speech speed, volume, verbosity. Persists to SharedPreferences. */
class Config(context: Context) {

    companion object {
        private const val PREFS_NAME = "atlas_sight_config"
        private const val KEY_SPEED = "speech_speed"
        private const val KEY_VOLUME = "volume"
        private const val KEY_VERBOSITY = "verbosity"
        private const val KEY_CONTINUOUS = "continuous_mode"
    }

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    private val _speechSpeed = MutableStateFlow(prefs.getFloat(KEY_SPEED, 1.0f))
    val speechSpeed: StateFlow<Float> = _speechSpeed.asStateFlow()

    private val _volume = MutableStateFlow(prefs.getFloat(KEY_VOLUME, 1.0f))
    val volume: StateFlow<Float> = _volume.asStateFlow()

    private val _verbosity = MutableStateFlow(
        try { Verbosity.valueOf(prefs.getString(KEY_VERBOSITY, "NORMAL") ?: "NORMAL") }
        catch (_: Exception) { Verbosity.NORMAL }
    )
    val verbosity: StateFlow<Verbosity> = _verbosity.asStateFlow()

    private val _continuousMode = MutableStateFlow(prefs.getBoolean(KEY_CONTINUOUS, true))
    val continuousMode: StateFlow<Boolean> = _continuousMode.asStateFlow()

    fun adjustSpeed(delta: Float) {
        _speechSpeed.value = (_speechSpeed.value + delta).coerceIn(0.5f, 3.0f)
        prefs.edit().putFloat(KEY_SPEED, _speechSpeed.value).apply()
    }

    fun setSpeed(speed: Float) {
        _speechSpeed.value = speed.coerceIn(0.5f, 3.0f)
        prefs.edit().putFloat(KEY_SPEED, _speechSpeed.value).apply()
    }

    fun adjustVolume(delta: Float) {
        _volume.value = (_volume.value + delta).coerceIn(0.1f, 1.0f)
        prefs.edit().putFloat(KEY_VOLUME, _volume.value).apply()
    }

    fun cycleVerbosity(): Verbosity {
        _verbosity.value = when (_verbosity.value) {
            Verbosity.BRIEF -> Verbosity.NORMAL
            Verbosity.NORMAL -> Verbosity.DETAILED
            Verbosity.DETAILED -> Verbosity.BRIEF
        }
        prefs.edit().putString(KEY_VERBOSITY, _verbosity.value.name).apply()
        return _verbosity.value
    }

    fun toggleContinuousMode(): Boolean {
        _continuousMode.value = !_continuousMode.value
        prefs.edit().putBoolean(KEY_CONTINUOUS, _continuousMode.value).apply()
        return _continuousMode.value
    }

    fun getSpeedForProfile(profile: SpeedProfile): Float = when (profile) {
        SpeedProfile.NAVIGATION -> 1.0f
        SpeedProfile.ALERT -> 0.85f
        SpeedProfile.GENERAL -> _speechSpeed.value
    }
}
