package dev.atlascortex.sight.platform

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineWhisperModelConfig
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import java.io.File

/**
 * Sherpa-ONNX Whisper offline STT — fully offline speech recognition.
 * Records audio from the microphone, accumulates ~3 seconds of speech,
 * then decodes with the Whisper model and emits the transcription.
 */
class SpeechRecognizer(private val context: Context) {

    companion object {
        private const val TAG = "SpeechRecognizer"
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL = AudioFormat.CHANNEL_IN_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        private const val CHUNK_SECONDS = 3
    }

    private var recognizer: OfflineRecognizer? = null
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
            val encoderFile = File(modelDir, "tiny.en-encoder.int8.onnx")
            val decoderFile = File(modelDir, "tiny.en-decoder.int8.onnx")
            val tokensFile = File(modelDir, "tiny.en-tokens.txt")

            Log.i(TAG, "Checking Whisper model files in ${modelDir.absolutePath}")
            if (modelDir.exists()) {
                val contents = modelDir.listFiles()?.map { "${it.name} (${it.length()} bytes)" }
                Log.i(TAG, "Directory contents: $contents")
            } else {
                Log.e(TAG, "Model directory does not exist: ${modelDir.absolutePath}")
                return@withContext false
            }

            val missing = mutableListOf<String>()
            if (!encoderFile.exists()) missing.add("encoder (${encoderFile.name})")
            if (!decoderFile.exists()) missing.add("decoder (${decoderFile.name})")
            if (!tokensFile.exists()) missing.add("tokens (${tokensFile.name})")

            if (missing.isNotEmpty()) {
                Log.e(TAG, "Missing Whisper model files: $missing")
                return@withContext false
            }

            Log.i(TAG, "Model files found — encoder: ${encoderFile.length() / 1_000_000}MB, decoder: ${decoderFile.length() / 1_000_000}MB, tokens: ${tokensFile.length()} bytes")

            val whisperConfig = OfflineWhisperModelConfig(
                encoder = encoderFile.absolutePath,
                decoder = decoderFile.absolutePath,
                language = "en",
                task = "transcribe",
            )
            val modelConfig = OfflineModelConfig(
                whisper = whisperConfig,
                tokens = tokensFile.absolutePath,
                numThreads = 2,
                provider = "cpu",
            )
            val config = OfflineRecognizerConfig(modelConfig = modelConfig)

            Log.i(TAG, "Creating OfflineRecognizer…")
            recognizer = OfflineRecognizer(config = config)
            Log.i(TAG, "Sherpa-ONNX Whisper STT initialized successfully")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize Whisper STT", e)
            recognizer = null
            false
        }
    }

    fun startListening() {
        if (isListening) {
            Log.d(TAG, "startListening: already listening")
            return
        }
        if (recognizer == null) {
            Log.w(TAG, "startListening: recognizer not initialized")
            return
        }
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            Log.e(TAG, "startListening: RECORD_AUDIO permission not granted")
            return
        }

        Log.i(TAG, "Starting microphone listening…")
        isListening = true
        job = scope.launch {
            recordAndRecognize()
        }
    }

    fun stopListening() {
        isListening = false
        job?.cancel()
        try { audioRecord?.stop() } catch (_: Exception) { }
        try { audioRecord?.release() } catch (_: Exception) { }
        audioRecord = null
    }

    fun shutdown() {
        stopListening()
        scope.cancel()
        recognizer?.release()
        recognizer = null
    }

    private suspend fun recordAndRecognize() {
        val bufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING)
            .coerceAtLeast(SAMPLE_RATE * 2)

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE, CHANNEL, ENCODING, bufferSize
            )
        } catch (e: SecurityException) {
            Log.e(TAG, "No RECORD_AUDIO permission", e)
            isListening = false
            return
        }

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord failed to initialize (state=${audioRecord?.state})")
            isListening = false
            return
        }

        audioRecord?.startRecording()
        Log.i(TAG, "AudioRecord started (bufferSize=$bufferSize, sampleRate=$SAMPLE_RATE)")

        val chunkSamples = SAMPLE_RATE * CHUNK_SECONDS
        val accumulator = mutableListOf<Float>()
        val buffer = ShortArray(bufferSize / 2)

        while (isListening) {
            val read = audioRecord?.read(buffer, 0, buffer.size) ?: break
            if (read > 0) {
                for (i in 0 until read) {
                    accumulator.add(buffer[i].toFloat() / Short.MAX_VALUE)
                }

                if (accumulator.size >= chunkSamples) {
                    val samples = accumulator.toFloatArray()
                    accumulator.clear()
                    decodeChunk(samples)
                }
            }
        }
    }

    private fun decodeChunk(samples: FloatArray) {
        val rec = recognizer ?: return
        try {
            val stream = rec.createStream()
            stream.acceptWaveform(samples, SAMPLE_RATE)
            rec.decode(stream)
            val result = rec.getResult(stream)
            stream.release()

            val text = result.text.trim()
            if (text.isNotBlank()) {
                Log.d(TAG, "Transcribed: $text")
                _transcriptions.tryEmit(text)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Whisper decode failed", e)
        }
    }
}
