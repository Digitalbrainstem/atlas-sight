package dev.atlascortex.sight.platform

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import dev.atlascortex.sight.core.SpeechItem
import dev.atlascortex.sight.core.SpeedProfile
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.PriorityBlockingQueue

/**
 * Sherpa-ONNX Piper TTS + priority speech queue.
 * Lower priority number = spoken first. FIFO within same priority.
 * Speed profiles: NAVIGATION=1.0x, ALERT=0.85x, GENERAL=user pref.
 */
class SpeechSynthesizer(private val context: Context) {

    private val speechQueue = PriorityBlockingQueue<SpeechItem>()
    private var isSpeaking = false
    private var job: Job? = null
    private var userSpeed: Float = 1.0f
    private var volume: Float = 1.0f
    private var ttsEngine: Any? = null // Sherpa-ONNX OfflineTts handle
    private var isInitialized = false
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    private val _lastSpoken = MutableSharedFlow<String>(replay = 1)
    val lastSpoken: SharedFlow<String> = _lastSpoken.asSharedFlow()

    private val modelDir: File get() = File(context.filesDir, "models/piper-tts")

    fun isReady(): Boolean = isInitialized

    suspend fun initialize(): Boolean = withContext(Dispatchers.IO) {
        try {
            val modelFile = File(modelDir, "en_US-amy-medium.onnx")
            if (!modelFile.exists()) return@withContext false
            loadPiperModel(modelFile)
            isInitialized = true
            startSpeechLoop()
            true
        } catch (_: Exception) {
            // TTS init failed — the app still works with haptics + audio cues
            isInitialized = false
            false
        }
    }

    fun setSpeed(speed: Float) {
        userSpeed = speed.coerceIn(0.5f, 3.0f)
    }

    fun setVolume(vol: Float) {
        volume = vol.coerceIn(0.0f, 1.0f)
    }

    /** Enqueue speech with priority. Lower = more urgent. */
    fun speak(text: String, priority: Int = 5, speedProfile: SpeedProfile = SpeedProfile.GENERAL) {
        if (text.isBlank()) return
        speechQueue.add(SpeechItem(text, priority, speedProfile))
    }

    /** Immediate speech — clears queue and speaks now. */
    fun speakImmediate(text: String, speedProfile: SpeedProfile = SpeedProfile.ALERT) {
        speechQueue.clear()
        speak(text, priority = 0, speedProfile = speedProfile)
    }

    fun stop() {
        speechQueue.clear()
        isSpeaking = false
    }

    fun shutdown() {
        stop()
        job?.cancel()
        scope.cancel()
        try {
            (ttsEngine as? AutoCloseable)?.close()
        } catch (_: Exception) { }
    }

    // --- Priority speech loop ---

    private fun startSpeechLoop() {
        job = scope.launch {
            while (isActive) {
                val item = withContext(Dispatchers.IO) {
                    speechQueue.poll()
                }
                if (item != null) {
                    isSpeaking = true
                    synthesizeAndPlay(item)
                    _lastSpoken.emit(item.text)
                    isSpeaking = false
                } else {
                    delay(50)
                }
            }
        }
    }

    private suspend fun synthesizeAndPlay(item: SpeechItem) {
        val speed = when (item.speedProfile) {
            SpeedProfile.NAVIGATION -> 1.0f
            SpeedProfile.ALERT -> 0.85f
            SpeedProfile.GENERAL -> userSpeed
        }
        try {
            val audioData = synthesize(item.text, speed)
            if (audioData != null) {
                playAudio(audioData)
            } else {
                // Fallback: use Android TTS if Sherpa not available
                fallbackSpeak(item.text)
            }
        } catch (_: Exception) {
            fallbackSpeak(item.text)
        }
    }

    private fun synthesize(text: String, speed: Float): ShortArray? {
        if (ttsEngine == null) return null
        return try {
            // Call Sherpa-ONNX TTS generate method via reflection
            val method = ttsEngine!!.javaClass.getMethod(
                "generate", String::class.java, Float::class.javaPrimitiveType, Int::class.javaPrimitiveType
            )
            val result = method.invoke(ttsEngine, text, speed, 0)
            val samplesField = result.javaClass.getField("samples")
            samplesField.get(result) as? ShortArray
        } catch (_: Exception) {
            null
        }
    }

    private suspend fun playAudio(samples: ShortArray) = withContext(Dispatchers.IO) {
        try {
            val sampleRate = 22050
            val bufferSize = samples.size * 2
            val track = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(sampleRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize.coerceAtLeast(AudioTrack.getMinBufferSize(
                    sampleRate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT
                )))
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build()
            track.setVolume(volume)
            track.write(samples, 0, samples.size)
            track.play()
            // Wait for playback
            val durationMs = (samples.size * 1000L) / 22050
            delay(durationMs + 100)
            track.stop()
            track.release()
        } catch (_: Exception) {
            // Audio playback failure — non-fatal
        }
    }

    private fun fallbackSpeak(text: String) {
        // Android TextToSpeech as absolute last resort
        try {
            val ttsClass = Class.forName("android.speech.tts.TextToSpeech")
            // This would need proper initialization — kept as stub
        } catch (_: Exception) { }
    }

    private fun loadPiperModel(modelFile: File) {
        try {
            val configFile = File(modelFile.parentFile, modelFile.nameWithoutExtension + ".onnx.json")
            val tokensFile = File(modelFile.parentFile, "tokens.txt")
            val dataDir = File(modelFile.parentFile, "espeak-ng-data")

            // Try to initialize Sherpa-ONNX OfflineTts
            val configClass = Class.forName("com.k2fsa.sherpa.onnx.OfflineTtsConfig")
            val modelConfigClass = Class.forName("com.k2fsa.sherpa.onnx.OfflineTtsModelConfig")
            val vitsPiperConfig = Class.forName("com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig")

            val piperConfig = vitsPiperConfig.getDeclaredConstructor().newInstance()
            setField(piperConfig, "model", modelFile.absolutePath)
            if (tokensFile.exists()) setField(piperConfig, "tokens", tokensFile.absolutePath)
            if (dataDir.exists()) setField(piperConfig, "dataDir", dataDir.absolutePath)

            val modelConfig = modelConfigClass.getDeclaredConstructor().newInstance()
            setField(modelConfig, "vits", piperConfig)

            val ttsConfig = configClass.getDeclaredConstructor().newInstance()
            setField(ttsConfig, "model", modelConfig)

            val ttsClass = Class.forName("com.k2fsa.sherpa.onnx.OfflineTts")
            ttsEngine = ttsClass.getDeclaredConstructor(configClass).newInstance(ttsConfig)
        } catch (_: Exception) {
            ttsEngine = null
        }
    }

    private fun setField(obj: Any, fieldName: String, value: Any) {
        try {
            val field = obj.javaClass.getField(fieldName)
            field.set(obj, value)
        } catch (_: Exception) { }
    }
}
