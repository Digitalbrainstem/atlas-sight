package dev.atlascortex.sight.platform

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import com.k2fsa.sherpa.onnx.GeneratedAudio
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig
import dev.atlascortex.sight.core.SpeechItem
import dev.atlascortex.sight.core.SpeedProfile
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import java.io.File
import java.util.concurrent.PriorityBlockingQueue

/**
 * Sherpa-ONNX Piper VITS offline TTS with priority speech queue.
 * Lower priority number = spoken first. FIFO within same priority.
 * Speed profiles: NAVIGATION=1.0x, ALERT=0.85x, GENERAL=user pref.
 */
class SpeechSynthesizer(private val context: Context) {

    companion object {
        private const val TAG = "SpeechSynthesizer"
    }

    private val speechQueue = PriorityBlockingQueue<SpeechItem>()
    private var isSpeaking = false
    private var job: Job? = null
    private var userSpeed: Float = 1.0f
    private var volume: Float = 1.0f
    private var tts: OfflineTts? = null
    private var sampleRate: Int = 22050
    private var isInitialized = false
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    private val _lastSpoken = MutableSharedFlow<String>(replay = 1)
    val lastSpoken: SharedFlow<String> = _lastSpoken.asSharedFlow()

    fun isReady(): Boolean = isInitialized

    suspend fun initialize(): Boolean = withContext(Dispatchers.IO) {
        try {
            val modelDir = File(context.filesDir, "models/piper-tts")
            if (!modelDir.isDirectory) {
                Log.w(TAG, "TTS model directory not found: ${modelDir.absolutePath}")
                return@withContext false
            }

            // Find the .onnx model file
            val modelFile = modelDir.listFiles()?.firstOrNull {
                it.name.endsWith(".onnx") && !it.name.endsWith(".onnx.json")
            }
            if (modelFile == null || !modelFile.exists()) {
                Log.w(TAG, "No .onnx model file found in ${modelDir.absolutePath}")
                return@withContext false
            }

            val tokensFile = File(modelDir, "tokens.txt")
            if (!tokensFile.exists()) {
                Log.w(TAG, "tokens.txt not found in ${modelDir.absolutePath}")
                return@withContext false
            }

            val espeakDataDir = File(modelDir, "espeak-ng-data")
            if (!espeakDataDir.isDirectory) {
                Log.w(TAG, "espeak-ng-data/ not found in ${modelDir.absolutePath}")
                return@withContext false
            }

            val vitsConfig = OfflineTtsVitsModelConfig(
                model = modelFile.absolutePath,
                tokens = tokensFile.absolutePath,
                dataDir = espeakDataDir.absolutePath,
            )
            val modelConfig = OfflineTtsModelConfig(
                vits = vitsConfig,
                numThreads = 2,
                provider = "cpu",
            )
            val ttsConfig = OfflineTtsConfig(model = modelConfig)

            tts = OfflineTts(config = ttsConfig)
            sampleRate = tts!!.sampleRate()
            isInitialized = true
            startSpeechLoop()
            Log.i(TAG, "Sherpa-ONNX Piper TTS initialized (sampleRate=$sampleRate)")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize Sherpa-ONNX TTS", e)
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

    fun speak(text: String, priority: Int = 5, speedProfile: SpeedProfile = SpeedProfile.GENERAL) {
        if (text.isBlank()) return
        speechQueue.add(SpeechItem(text, priority, speedProfile))
    }

    fun speakImmediate(text: String, speedProfile: SpeedProfile = SpeedProfile.ALERT) {
        speechQueue.clear()
        currentTrack?.stop()
        speak(text, priority = 0, speedProfile = speedProfile)
    }

    fun stop() {
        speechQueue.clear()
        currentTrack?.stop()
        isSpeaking = false
    }

    fun shutdown() {
        stop()
        job?.cancel()
        scope.cancel()
        tts?.release()
        tts = null
    }

    @Volatile
    private var currentTrack: AudioTrack? = null

    private fun startSpeechLoop() {
        job = scope.launch {
            while (isActive) {
                val item = withContext(Dispatchers.IO) {
                    speechQueue.poll()
                }
                if (item != null) {
                    isSpeaking = true
                    speakItem(item)
                    _lastSpoken.emit(item.text)
                    isSpeaking = false
                } else {
                    delay(50)
                }
            }
        }
    }

    private suspend fun speakItem(item: SpeechItem) = withContext(Dispatchers.IO) {
        val engine = tts ?: return@withContext

        val speed = when (item.speedProfile) {
            SpeedProfile.NAVIGATION -> 1.0f
            SpeedProfile.ALERT -> 0.85f
            SpeedProfile.GENERAL -> userSpeed
        }

        try {
            val audio: GeneratedAudio = engine.generate(
                text = item.text,
                sid = 0,
                speed = speed,
            )

            if (audio.samples.isEmpty()) return@withContext
            playAudio(audio.samples, audio.sampleRate)
        } catch (e: Exception) {
            Log.e(TAG, "TTS generation failed for: ${item.text}", e)
        }
    }

    private fun playAudio(samples: FloatArray, rate: Int) {
        val pcm = ShortArray(samples.size) {
            (samples[it] * Short.MAX_VALUE * volume).toInt().coerceIn(
                Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt()
            ).toShort()
        }

        val bufferSize = pcm.size * 2
        val track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(rate)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .build()
            )
            .setBufferSizeInBytes(bufferSize)
            .setTransferMode(AudioTrack.MODE_STATIC)
            .build()

        currentTrack = track
        track.write(pcm, 0, pcm.size)
        track.play()

        // Wait for playback to finish
        val durationMs = (pcm.size.toLong() * 1000L) / rate
        Thread.sleep(durationMs + 50)

        track.stop()
        track.release()
        currentTrack = null
    }
}
