package dev.atlascortex.sight.util

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * First-run model download with voice progress announcements.
 * Downloads Qwen3-VL-2B, Whisper STT, and Piper TTS models.
 */
class ModelDownloader(private val context: Context) {

    data class DownloadProgress(
        val modelName: String,
        val progress: Float, // 0.0 to 1.0
        val isComplete: Boolean = false,
        val error: String? = null,
    )

    private val _progress = MutableStateFlow(DownloadProgress("", 0f))
    val progress: StateFlow<DownloadProgress> = _progress.asStateFlow()

    private val _overallStatus = MutableStateFlow("Checking models…")
    val overallStatus: StateFlow<String> = _overallStatus.asStateFlow()

    /** Model definitions with download URLs. */
    data class ModelInfo(
        val name: String,
        val displayName: String,
        val url: String,
        val targetDir: String,
        val targetFile: String,
        val sizeDescription: String,
    )

    private val models = listOf(
        ModelInfo(
            name = "qwen3-vl",
            displayName = "Vision AI",
            url = "https://huggingface.co/unsloth/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3-VL-2B-Instruct-Q4_K_M.gguf",
            targetDir = "models/qwen3-vl",
            targetFile = "Qwen3-VL-2B-Instruct-Q4_K_M.gguf",
            sizeDescription = "1.1 gigabytes",
        ),
        ModelInfo(
            name = "whisper-stt",
            displayName = "Speech recognition",
            url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.en.tar.bz2",
            targetDir = "models/whisper-stt",
            targetFile = "sherpa-onnx-whisper-tiny.en.tar.bz2",
            sizeDescription = "118 megabytes",
        ),
        ModelInfo(
            name = "piper-tts",
            displayName = "Voice synthesis",
            url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx",
            targetDir = "models/piper-tts",
            targetFile = "en_US-amy-medium.onnx",
            sizeDescription = "63 megabytes",
        ),
        ModelInfo(
            name = "piper-tts-config",
            displayName = "Voice configuration",
            url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json",
            targetDir = "models/piper-tts",
            targetFile = "en_US-amy-medium.onnx.json",
            sizeDescription = "5 kilobytes",
        ),
    )

    /** Check which models are already downloaded. */
    fun getModelStatus(): Map<String, Boolean> =
        models.associate { model ->
            val file = File(context.filesDir, "${model.targetDir}/${model.targetFile}")
            model.name to file.exists()
        }

    /** Check if all required models are present. */
    fun allModelsReady(): Boolean = getModelStatus().values.all { it }

    /** Get total download size description. */
    fun getTotalSizeDescription(): String = "about 1.3 gigabytes"

    /** Download all missing models. Returns voice announcement strings for progress. */
    suspend fun downloadMissingModels(
        onAnnounce: (String) -> Unit,
    ): Boolean = withContext(Dispatchers.IO) {
        val status = getModelStatus()
        val missing = models.filter { !(status[it.name] ?: false) }

        if (missing.isEmpty()) {
            onAnnounce("All AI models are ready.")
            return@withContext true
        }

        onAnnounce(
            "Welcome to Atlas Sight. Downloading AI models. " +
            "This only happens once and requires about 1 gigabyte."
        )

        for ((index, model) in missing.withIndex()) {
            val modelNum = index + 1
            val totalModels = missing.size
            onAnnounce(
                "Downloading ${model.displayName}, " +
                "${model.sizeDescription}. Model $modelNum of $totalModels."
            )

            val success = downloadModel(model, onAnnounce)
            if (!success) {
                onAnnounce(
                    "Failed to download ${model.displayName}. " +
                    "Please check your internet connection and try again."
                )
                return@withContext false
            }
        }

        onAnnounce("All models downloaded. Atlas Sight is ready. Double-tap or say Hey Atlas to begin.")
        true
    }

    private suspend fun downloadModel(
        model: ModelInfo,
        onAnnounce: (String) -> Unit,
    ): Boolean = withContext(Dispatchers.IO) {
        try {
            val dir = File(context.filesDir, model.targetDir)
            dir.mkdirs()
            val targetFile = File(dir, model.targetFile)
            val tempFile = File(dir, "${model.targetFile}.downloading")

            val url = URL(model.url)
            val connection = url.openConnection() as HttpURLConnection
            connection.connectTimeout = 30000
            connection.readTimeout = 30000
            connection.requestMethod = "GET"

            if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                return@withContext false
            }

            val totalSize = connection.contentLengthLong
            var downloaded = 0L
            var lastAnnouncedPercent = 0

            connection.inputStream.use { input ->
                FileOutputStream(tempFile).use { output ->
                    val buffer = ByteArray(8192)
                    var read: Int
                    while (input.read(buffer).also { read = it } != -1) {
                        output.write(buffer, 0, read)
                        downloaded += read

                        // Progress update
                        if (totalSize > 0) {
                            val percent = ((downloaded * 100) / totalSize).toInt()
                            _progress.value = DownloadProgress(
                                model.displayName,
                                downloaded.toFloat() / totalSize.toFloat(),
                            )
                            // Announce every 25%
                            val milestone = (percent / 25) * 25
                            if (milestone > lastAnnouncedPercent && milestone > 0) {
                                lastAnnouncedPercent = milestone
                                onAnnounce("${model.displayName}: $milestone percent complete.")
                            }
                        }
                    }
                }
            }

            // Rename temp to final
            tempFile.renameTo(targetFile)
            _progress.value = DownloadProgress(model.displayName, 1f, isComplete = true)
            true
        } catch (e: Exception) {
            _progress.value = DownloadProgress(model.displayName, 0f, error = e.message)
            false
        }
    }
}
