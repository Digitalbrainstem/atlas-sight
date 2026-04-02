package dev.atlascortex.sight

import android.app.Application
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import java.io.File
import java.io.FileWriter
import java.io.PrintWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.sin

/**
 * Application-level initialization.
 * Installs a global crash handler that logs to file and speaks before dying.
 */
class SightApplication : Application() {
    companion object {
        const val TAG = "AtlasSight"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "Atlas Sight application starting")
        installCrashHandler()
    }

    private fun installCrashHandler() {
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()

        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                Log.e(TAG, "UNCAUGHT EXCEPTION on thread ${thread.name}", throwable)
                writeCrashLog(thread, throwable)
            } catch (_: Exception) { }

            try {
                speakCrashMessage()
            } catch (_: Exception) { }

            // Delegate to the default handler (kills the process)
            defaultHandler?.uncaughtException(thread, throwable)
        }
    }

    private fun writeCrashLog(thread: Thread, throwable: Throwable) {
        try {
            val logDir = File(filesDir, "crash-logs")
            logDir.mkdirs()

            // Keep only the 10 most recent crash logs
            logDir.listFiles()
                ?.sortedByDescending { it.lastModified() }
                ?.drop(9)
                ?.forEach { it.delete() }

            val timestamp = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date())
            val logFile = File(logDir, "crash-$timestamp.txt")

            PrintWriter(FileWriter(logFile)).use { pw ->
                pw.println("Atlas Sight Crash Report")
                pw.println("========================")
                pw.println("Time: ${Date()}")
                pw.println("Thread: ${thread.name} (id=${thread.id})")
                pw.println("Device: ${android.os.Build.MODEL} (${android.os.Build.DEVICE})")
                pw.println("Android: ${android.os.Build.VERSION.RELEASE} (API ${android.os.Build.VERSION.SDK_INT})")
                pw.println()
                pw.println("Available memory: ${Runtime.getRuntime().freeMemory() / 1_000_000}MB free / ${Runtime.getRuntime().maxMemory() / 1_000_000}MB max")
                pw.println()
                pw.println("Exception:")
                throwable.printStackTrace(pw)
            }

            Log.i(TAG, "Crash log written to ${logFile.absolutePath}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to write crash log", e)
        }
    }

    /**
     * Best-effort spoken crash message using raw AudioTrack (no TTS dependency).
     * Plays a descending tone sequence as audible alert since full TTS may be unavailable.
     */
    private fun speakCrashMessage() {
        try {
            val sampleRate = 22050
            val toneMs = 200
            val numSamples = sampleRate * toneMs / 1000
            val fadeSamples = 44

            // Three descending tones: 1000Hz → 700Hz → 400Hz (error sound)
            val frequencies = floatArrayOf(1000f, 700f, 400f)
            val gapSamples = sampleRate * 80 / 1000
            val totalSamples = frequencies.size * numSamples + (frequencies.size - 1) * gapSamples
            val samples = ShortArray(totalSamples)
            var idx = 0

            for ((fi, freq) in frequencies.withIndex()) {
                for (i in 0 until numSamples) {
                    val t = i.toDouble() / sampleRate
                    val value = sin(2.0 * PI * freq * t) * Short.MAX_VALUE * 0.8
                    val fadeIn = min(i, fadeSamples).toDouble() / fadeSamples
                    val fadeOut = min(numSamples - 1 - i, fadeSamples).toDouble() / fadeSamples
                    samples[idx++] = (value * fadeIn * fadeOut).toInt().toShort()
                }
                if (fi < frequencies.size - 1) {
                    for (i in 0 until gapSamples) {
                        samples[idx++] = 0
                    }
                }
            }

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
                        .setSampleRate(sampleRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build()

            track.write(samples, 0, samples.size)
            track.play()

            // Wait for playback to complete
            val durationMs = (samples.size.toLong() * 1000L) / sampleRate + 100
            Thread.sleep(durationMs)

            try { track.stop() } catch (_: Exception) { }
            try { track.release() } catch (_: Exception) { }
        } catch (_: Exception) {
            // Best-effort — if audio fails, we still crash-log
        }
    }
}
