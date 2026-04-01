package dev.atlascortex.sight.platform

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import dev.atlascortex.sight.core.HapticPattern

/**
 * 6 vibration patterns for accessibility feedback.
 * Each pattern has specific timing and meaning.
 */
class HapticEngine(context: Context) {

    private val vibrator: Vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager)
            .defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
    }

    private var heartbeatActive = false

    fun vibrate(pattern: HapticPattern) {
        if (!vibrator.hasVibrator()) return

        when (pattern) {
            HapticPattern.ACKNOWLEDGE -> singlePulse()
            HapticPattern.SUCCESS -> doublePulse()
            HapticPattern.WARNING -> triplePulse()
            HapticPattern.DANGER -> rapidFive()
            HapticPattern.HEARTBEAT -> startHeartbeat()
            HapticPattern.NAVIGATE -> navigatePattern()
        }
    }

    fun stopHeartbeat() {
        heartbeatActive = false
        vibrator.cancel()
    }

    fun cancel() {
        heartbeatActive = false
        vibrator.cancel()
    }

    /** Single 100ms pulse — command acknowledged. */
    private fun singlePulse() {
        vibrator.vibrate(
            VibrationEffect.createOneShot(100, VibrationEffect.DEFAULT_AMPLITUDE)
        )
    }

    /** 60ms + 80ms gap + 60ms — success/ready. */
    private fun doublePulse() {
        vibrator.vibrate(
            VibrationEffect.createWaveform(
                longArrayOf(0, 60, 80, 60), // wait, on, off, on
                intArrayOf(0, VibrationEffect.DEFAULT_AMPLITUDE, 0, VibrationEffect.DEFAULT_AMPLITUDE),
                -1 // no repeat
            )
        )
    }

    /** 120ms x 3 — warning. */
    private fun triplePulse() {
        vibrator.vibrate(
            VibrationEffect.createWaveform(
                longArrayOf(0, 120, 80, 120, 80, 120),
                intArrayOf(0, VibrationEffect.DEFAULT_AMPLITUDE, 0, VibrationEffect.DEFAULT_AMPLITUDE, 0, VibrationEffect.DEFAULT_AMPLITUDE),
                -1
            )
        )
    }

    /** 50ms x 5 with 30ms gaps — DANGER, stop moving. */
    private fun rapidFive() {
        vibrator.vibrate(
            VibrationEffect.createWaveform(
                longArrayOf(0, 50, 30, 50, 30, 50, 30, 50, 30, 50),
                intArrayOf(0, 255, 0, 255, 0, 255, 0, 255, 0, 255),
                -1
            )
        )
    }

    /** 100ms on, 600ms off — continuous mode active. Loops until stopped. */
    private fun startHeartbeat() {
        heartbeatActive = true
        vibrator.vibrate(
            VibrationEffect.createWaveform(
                longArrayOf(0, 100, 600),
                intArrayOf(0, VibrationEffect.DEFAULT_AMPLITUDE, 0),
                0 // repeat from index 0
            )
        )
    }

    /** 70ms x 3 with 100ms gaps — navigation active. */
    private fun navigatePattern() {
        vibrator.vibrate(
            VibrationEffect.createWaveform(
                longArrayOf(0, 70, 100, 70, 100, 70),
                intArrayOf(0, VibrationEffect.DEFAULT_AMPLITUDE, 0, VibrationEffect.DEFAULT_AMPLITUDE, 0, VibrationEffect.DEFAULT_AMPLITUDE),
                -1
            )
        )
    }
}
