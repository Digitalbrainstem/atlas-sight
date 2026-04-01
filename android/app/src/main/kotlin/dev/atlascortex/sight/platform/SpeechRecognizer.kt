package dev.atlascortex.sight.platform

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import java.io.File

/**
 * Sherpa-ONNX Whisper STT — fully offline speech recognition.
 * Streams audio from the microphone and emits recognized text.
 */
class SpeechRecognizer(private val context: Context) {

    companion object {
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL = AudioFormat.CHANNEL_IN_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
    }

    private var recognizer: Any? = null // Sherpa-ONNX OnlineRecognizer
    private var audioRecord: AudioRecord? = null
    private var isListening = false
    private var job: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private val _transcriptions = MutableSharedFlow<String>(extraBufferCapacity = 10)
    val transcriptions: SharedFlow<String> = _transcriptions.asSharedFlow()

    private val modelDir: File get() = File(context.filesDir, "models/whisper-stt")

    fun isReady(): Boolean = recognizer != null

    suspend fun initialize(): Boolean = withContext(Dispatchers.IO) {
        try {
            val encoderFile = File(modelDir, "whisper-small-encoder.onnx")
            val decoderFile = File(modelDir, "whisper-small-decoder.onnx")
            if (!encoderFile.exists() || !decoderFile.exists()) return@withContext false
            loadWhisperModel(encoderFile, decoderFile)
            true
        } catch (_: Exception) {
            false
        }
    }

    fun startListening() {
        if (isListening) return
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) return

        isListening = true
        job = scope.launch {
            recordAndRecognize()
        }
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
        try {
            (recognizer as? AutoCloseable)?.close()
        } catch (_: Exception) { }
        recognizer = null
    }

    private suspend fun recordAndRecognize() {
        val bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING)
            .coerceAtLeast(SAMPLE_RATE * 2) // At least 1 second buffer

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            SAMPLE_RATE, CHANNEL, ENCODING, bufferSize
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            isListening = false
            return
        }

        audioRecord?.startRecording()
        val buffer = ShortArray(bufferSize / 2)

        while (isListening) {
            val read = audioRecord?.read(buffer, 0, buffer.size) ?: break
            if (read > 0) {
                processAudioChunk(buffer, read)
            }
        }
    }

    private fun processAudioChunk(samples: ShortArray, count: Int) {
        if (recognizer == null) return
        try {
            // Feed audio to Sherpa-ONNX recognizer
            val floatSamples = FloatArray(count) { samples[it].toFloat() / Short.MAX_VALUE }
            feedAudioToRecognizer(floatSamples)

            // Check for results
            val text = getRecognizerResult()
            if (text.isNotBlank()) {
                _transcriptions.tryEmit(text.trim())
            }
        } catch (_: Exception) { }
    }

    private fun feedAudioToRecognizer(samples: FloatArray) {
        try {
            val stream = recognizer!!.javaClass.getMethod("createStream").invoke(recognizer)
            stream.javaClass.getMethod("acceptWaveform", FloatArray::class.java, Int::class.javaPrimitiveType)
                .invoke(stream, samples, SAMPLE_RATE)
            recognizer!!.javaClass.getMethod("decode", stream.javaClass).invoke(recognizer, stream)
        } catch (_: Exception) { }
    }

    private fun getRecognizerResult(): String {
        return try {
            val result = recognizer!!.javaClass.getMethod("getResult").invoke(recognizer)
            result?.javaClass?.getMethod("getText")?.invoke(result)?.toString() ?: ""
        } catch (_: Exception) {
            ""
        }
    }

    private fun loadWhisperModel(encoder: File, decoder: File) {
        try {
            val configClass = Class.forName("com.k2fsa.sherpa.onnx.OnlineRecognizerConfig")
            val modelConfigClass = Class.forName("com.k2fsa.sherpa.onnx.OnlineModelConfig")
            val whisperConfigClass = Class.forName("com.k2fsa.sherpa.onnx.OnlineWhisperModelConfig")

            val whisperConfig = whisperConfigClass.getDeclaredConstructor().newInstance()
            setField(whisperConfig, "encoder", encoder.absolutePath)
            setField(whisperConfig, "decoder", decoder.absolutePath)

            val modelConfig = modelConfigClass.getDeclaredConstructor().newInstance()
            setField(modelConfig, "whisper", whisperConfig)

            val tokensFile = File(modelDir, "tokens.txt")
            if (tokensFile.exists()) setField(modelConfig, "tokens", tokensFile.absolutePath)

            val config = configClass.getDeclaredConstructor().newInstance()
            setField(config, "modelConfig", modelConfig)

            val recognizerClass = Class.forName("com.k2fsa.sherpa.onnx.OnlineRecognizer")
            recognizer = recognizerClass.getDeclaredConstructor(configClass).newInstance(config)
        } catch (_: Exception) {
            recognizer = null
        }
    }

    private fun setField(obj: Any, fieldName: String, value: Any) {
        try {
            val field = obj.javaClass.getField(fieldName)
            field.set(obj, value)
        } catch (_: Exception) { }
    }
}
