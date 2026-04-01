package dev.atlascortex.sight.platform

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import java.io.File

/**
 * Wake word detector — "Hey Atlas" / "Atlas" keyword spotting.
 * Uses Sherpa-ONNX KeywordSpotter or simple energy + pattern detection.
 */
class WakeWordDetector(private val context: Context) {

    companion object {
        private const val SAMPLE_RATE = 16000
        private val WAKE_WORDS = listOf("hey atlas", "atlas")
    }

    private var keywordSpotter: Any? = null
    private var audioRecord: AudioRecord? = null
    private var isListening = false
    private var job: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private val _wakeWordDetected = MutableSharedFlow<String>(extraBufferCapacity = 5)
    val wakeWordDetected: SharedFlow<String> = _wakeWordDetected.asSharedFlow()

    private val modelDir: File get() = File(context.filesDir, "models/wake-word")

    fun isReady(): Boolean = true // Can fallback to text-based detection

    suspend fun initialize(): Boolean = withContext(Dispatchers.IO) {
        try {
            val modelFile = File(modelDir, "keywords.onnx")
            if (modelFile.exists()) {
                loadKeywordSpotter(modelFile)
            }
            true
        } catch (_: Exception) {
            true // Still works via text-based detection
        }
    }

    /** Check transcribed text for wake words (fallback when no KWS model). */
    fun checkTranscription(text: String): Boolean {
        val lower = text.lowercase().trim()
        return WAKE_WORDS.any { lower.startsWith(it) || lower.contains(it) }
    }

    /** Strip the wake word from transcribed text to get the command. */
    fun stripWakeWord(text: String): String {
        var result = text.trim()
        for (word in WAKE_WORDS.sortedByDescending { it.length }) {
            val regex = Regex("(?i)^\\s*$word[,.]?\\s*")
            result = result.replace(regex, "")
        }
        return result.trim()
    }

    fun startListening() {
        if (isListening || keywordSpotter == null) return
        isListening = true
        job = scope.launch { listenForWakeWord() }
    }

    fun stopListening() {
        isListening = false
        job?.cancel()
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
    }

    fun shutdown() {
        stopListening()
        scope.cancel()
    }

    private suspend fun listenForWakeWord() {
        val bufferSize = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        ).coerceAtLeast(SAMPLE_RATE * 2)

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )
        } catch (_: SecurityException) {
            isListening = false
            return
        }

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            isListening = false
            return
        }

        audioRecord?.startRecording()
        val buffer = ShortArray(bufferSize / 2)

        while (isListening) {
            val read = audioRecord?.read(buffer, 0, buffer.size) ?: break
            if (read > 0 && keywordSpotter != null) {
                val detected = processAudio(buffer, read)
                if (detected) {
                    _wakeWordDetected.tryEmit("atlas")
                }
            }
        }
    }

    private fun processAudio(samples: ShortArray, count: Int): Boolean {
        return try {
            val floats = FloatArray(count) { samples[it].toFloat() / Short.MAX_VALUE }
            val stream = keywordSpotter!!.javaClass.getMethod("createStream")
                .invoke(keywordSpotter)
            stream.javaClass.getMethod("acceptWaveform", FloatArray::class.java, Int::class.javaPrimitiveType)
                .invoke(stream, floats, SAMPLE_RATE)
            val isReady = keywordSpotter!!.javaClass.getMethod("isReady", stream.javaClass)
                .invoke(keywordSpotter, stream) as Boolean
            if (isReady) {
                keywordSpotter!!.javaClass.getMethod("decode", stream.javaClass)
                    .invoke(keywordSpotter, stream)
                val result = keywordSpotter!!.javaClass.getMethod("getResult", stream.javaClass)
                    .invoke(keywordSpotter, stream)
                val keyword = result.toString()
                keyword.isNotBlank()
            } else {
                false
            }
        } catch (_: Exception) {
            false
        }
    }

    private fun loadKeywordSpotter(modelFile: File) {
        try {
            val configClass = Class.forName("com.k2fsa.sherpa.onnx.KeywordSpotterConfig")
            val config = configClass.getDeclaredConstructor().newInstance()
            setField(config, "modelFile", modelFile.absolutePath)
            val kwsClass = Class.forName("com.k2fsa.sherpa.onnx.KeywordSpotter")
            keywordSpotter = kwsClass.getDeclaredConstructor(configClass).newInstance(config)
        } catch (_: Exception) {
            keywordSpotter = null
        }
    }

    private fun setField(obj: Any, fieldName: String, value: Any) {
        try {
            obj.javaClass.getField(fieldName).set(obj, value)
        } catch (_: Exception) { }
    }
}
