package dev.atlascortex.sight.core

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.sin

/**
 * Synthesized sine-wave audio cues — zero audio files shipped.
 * 22050 Hz sample rate, 16-bit PCM, 2ms fade-in/out to prevent clicks.
 */
class AudioCues {
    companion object {
        private const val SAMPLE_RATE = 22050
        private const val FADE_SAMPLES = 44 // ~2ms at 22050 Hz
    }

    private var volume: Float = 1.0f

    fun setVolume(vol: Float) {
        volume = vol.coerceIn(0.0f, 1.0f)
    }

    fun play(cue: AudioCueType) {
        val samples = when (cue) {
            AudioCueType.BEEP -> generateTone(800f, 100)
            AudioCueType.CHIME -> generateSweep(1000f, 1250f, 200)
            AudioCueType.WARNING -> generateSweep(1200f, 1800f, 400)
            AudioCueType.DANGER -> generatePulsing(1600f, 5, 80, 40)
            AudioCueType.RISING -> generateSweep(600f, 1400f, 300)
            AudioCueType.FALLING -> generateSweep(1400f, 600f, 300)
            AudioCueType.MODE_SWITCH -> generateTwoTone(880f, 1100f, 100, 100)
        }
        playPcm(samples)
    }

    /** Constant-frequency tone. */
    private fun generateTone(freq: Float, durationMs: Int): ShortArray {
        val numSamples = (SAMPLE_RATE * durationMs / 1000.0).toInt()
        val samples = ShortArray(numSamples)
        for (i in samples.indices) {
            val t = i.toDouble() / SAMPLE_RATE
            val value = sin(2.0 * PI * freq * t) * Short.MAX_VALUE * volume
            samples[i] = applyFade(value, i, numSamples).toInt().toShort()
        }
        return samples
    }

    /** Linear frequency sweep. */
    private fun generateSweep(startFreq: Float, endFreq: Float, durationMs: Int): ShortArray {
        val numSamples = (SAMPLE_RATE * durationMs / 1000.0).toInt()
        val samples = ShortArray(numSamples)
        var phase = 0.0
        for (i in samples.indices) {
            val progress = i.toDouble() / numSamples
            val freq = startFreq + (endFreq - startFreq) * progress
            phase += 2.0 * PI * freq / SAMPLE_RATE
            val value = sin(phase) * Short.MAX_VALUE * volume
            samples[i] = applyFade(value, i, numSamples).toInt().toShort()
        }
        return samples
    }

    /** Pulsing tone (danger alert). */
    private fun generatePulsing(freq: Float, pulses: Int, onMs: Int, offMs: Int): ShortArray {
        val onSamples = (SAMPLE_RATE * onMs / 1000.0).toInt()
        val offSamples = (SAMPLE_RATE * offMs / 1000.0).toInt()
        val totalSamples = pulses * (onSamples + offSamples)
        val samples = ShortArray(totalSamples)
        var idx = 0
        for (p in 0 until pulses) {
            for (i in 0 until onSamples) {
                val t = i.toDouble() / SAMPLE_RATE
                val value = sin(2.0 * PI * freq * t) * Short.MAX_VALUE * volume
                if (idx < samples.size) {
                    samples[idx] = applyFade(value, i, onSamples).toInt().toShort()
                }
                idx++
            }
            // Silence gap
            for (i in 0 until offSamples) {
                if (idx < samples.size) samples[idx] = 0
                idx++
            }
        }
        return samples
    }

    /** Two-tone sweep for mode switch. */
    private fun generateTwoTone(freq1: Float, freq2: Float, dur1Ms: Int, dur2Ms: Int): ShortArray {
        val tone1 = generateTone(freq1, dur1Ms)
        val silence = ShortArray((SAMPLE_RATE * 30 / 1000.0).toInt()) // 30ms gap
        val tone2 = generateTone(freq2, dur2Ms)
        return tone1 + silence + tone2
    }

    /** Apply 2ms fade-in/out to prevent clicks. */
    private fun applyFade(value: Double, index: Int, total: Int): Double {
        val fadeIn = min(index, FADE_SAMPLES).toDouble() / FADE_SAMPLES
        val fadeOut = min(total - 1 - index, FADE_SAMPLES).toDouble() / FADE_SAMPLES
        return value * fadeIn * fadeOut
    }

    private fun playPcm(samples: ShortArray) {
        try {
            val bufferSize = samples.size * 2
            val track = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(SAMPLE_RATE)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build()
            track.write(samples, 0, samples.size)
            track.play()
            // Release after playback via marker; schedule fallback release in case marker never fires
            track.setNotificationMarkerPosition(samples.size)
            track.setPlaybackPositionUpdateListener(object : AudioTrack.OnPlaybackPositionUpdateListener {
                override fun onMarkerReached(t: AudioTrack) {
                    try { t.stop() } catch (_: Exception) { }
                    try { t.release() } catch (_: Exception) { }
                }
                override fun onPeriodicNotification(t: AudioTrack) {}
            })
            // Fallback: release after estimated duration + generous margin
            val durationMs = (samples.size.toLong() * 1000L) / SAMPLE_RATE + 500
            Thread {
                try {
                    Thread.sleep(durationMs)
                    track.stop()
                } catch (_: Exception) { }
                try { track.release() } catch (_: Exception) { }
            }.start()
        } catch (_: Exception) {
            // Audio playback is best-effort — never crash
        }
    }
}
