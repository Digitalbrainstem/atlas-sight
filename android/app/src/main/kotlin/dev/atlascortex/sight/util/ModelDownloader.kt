package dev.atlascortex.sight.util

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream
import java.io.BufferedInputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * First-run model download with voice progress announcements.
 * Downloads Qwen3-VL-2B, Whisper STT (tarball), and Piper TTS (tarball).
 * Tarballs are extracted after download using Apache Commons Compress.
 */
class ModelDownloader(private val context: Context) {

    companion object {
        private const val TAG = "ModelDownloader"
    }

    data class DownloadProgress(
        val modelName: String,
        val progress: Float,
        val isComplete: Boolean = false,
        val error: String? = null,
    )

    private val _progress = MutableStateFlow(DownloadProgress("", 0f))
    val progress: StateFlow<DownloadProgress> = _progress.asStateFlow()

    private val _overallStatus = MutableStateFlow("Checking models…")
    val overallStatus: StateFlow<String> = _overallStatus.asStateFlow()

    data class ModelInfo(
        val name: String,
        val displayName: String,
        val url: String,
        val targetDir: String,
        val targetFile: String,
        val sizeDescription: String,
        val isTarball: Boolean = false,
    )

    private val models = listOf(
        ModelInfo(
            name = "qwen3-vl",
            displayName = "Vision AI text model",
            url = "https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3VL-2B-Instruct-Q4_K_M.gguf",
            targetDir = "models/qwen3-vl",
            targetFile = "Qwen3-VL-2B-Instruct-Q4_K_M.gguf",
            sizeDescription = "1.1 gigabytes",
        ),
        ModelInfo(
            name = "qwen3-vl-mmproj",
            displayName = "Vision AI eye module",
            url = "https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
            targetDir = "models/qwen3-vl",
            targetFile = "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
            sizeDescription = "445 megabytes",
        ),
        ModelInfo(
            name = "whisper-stt",
            displayName = "Speech recognition",
            url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.en.tar.bz2",
            targetDir = "models/whisper-stt",
            targetFile = "sherpa-onnx-whisper-tiny.en.tar.bz2",
            sizeDescription = "118 megabytes",
            isTarball = true,
        ),
        ModelInfo(
            name = "piper-tts",
            displayName = "Voice synthesis",
            url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-kristin-medium.tar.bz2",
            targetDir = "models/piper-tts",
            targetFile = "vits-piper-en_US-kristin-medium.tar.bz2",
            sizeDescription = "67 megabytes",
            isTarball = true,
        ),
    )

    /** Check which models are ready (extracted if tarball, downloaded if plain). */
    fun getModelStatus(): Map<String, Boolean> =
        models.associate { model ->
            model.name to isModelReady(model)
        }

    private fun isModelReady(model: ModelInfo): Boolean {
        val dir = File(context.filesDir, model.targetDir)
        return when (model.name) {
            "whisper-stt" -> {
                File(dir, "tiny.en-encoder.int8.onnx").exists() &&
                File(dir, "tiny.en-decoder.int8.onnx").exists() &&
                File(dir, "tiny.en-tokens.txt").exists()
            }
            "piper-tts" -> {
                File(dir, "tokens.txt").exists() &&
                File(dir, "espeak-ng-data").isDirectory
            }
            else -> File(dir, model.targetFile).exists()
        }
    }

    fun allModelsReady(): Boolean = getModelStatus().values.all { it }

    fun getTotalSizeDescription(): String = "about 1.8 gigabytes"

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

            val finalConnection = openConnectionWithRedirects(model.url)
                ?: run {
                    onAnnounce("Could not connect to download ${model.displayName}.")
                    return@withContext false
                }

            if (finalConnection.responseCode != HttpURLConnection.HTTP_OK) {
                onAnnounce("Server returned error ${finalConnection.responseCode} for ${model.displayName}.")
                return@withContext false
            }

            val totalSize = finalConnection.contentLengthLong
            var downloaded = 0L
            var lastAnnouncedPercent = 0

            finalConnection.inputStream.use { input ->
                FileOutputStream(tempFile).use { output ->
                    val buffer = ByteArray(65536)
                    var read: Int
                    while (input.read(buffer).also { read = it } != -1) {
                        output.write(buffer, 0, read)
                        downloaded += read

                        if (totalSize > 0) {
                            val percent = ((downloaded * 100) / totalSize).toInt()
                            _progress.value = DownloadProgress(
                                model.displayName,
                                downloaded.toFloat() / totalSize.toFloat(),
                            )
                            val milestone = (percent / 25) * 25
                            if (milestone > lastAnnouncedPercent && milestone > 0) {
                                lastAnnouncedPercent = milestone
                                onAnnounce("${model.displayName}: $milestone percent complete.")
                            }
                        }
                    }
                }
            }

            tempFile.renameTo(targetFile)

            if (model.isTarball) {
                onAnnounce("Extracting ${model.displayName}…")
                extractTarBz2(targetFile, dir)
                targetFile.delete()
            }

            _progress.value = DownloadProgress(model.displayName, 1f, isComplete = true)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Download failed for ${model.name}", e)
            _progress.value = DownloadProgress(model.displayName, 0f, error = e.message)
            false
        }
    }

    private fun openConnectionWithRedirects(urlStr: String): HttpURLConnection? {
        var connection = (URL(urlStr).openConnection() as HttpURLConnection).apply {
            connectTimeout = 30_000
            readTimeout = 60_000
            requestMethod = "GET"
            instanceFollowRedirects = true
            setRequestProperty("User-Agent", "AtlasSight/1.0")
        }

        var redirects = 0
        while (redirects < 5) {
            val code = connection.responseCode
            if (code in listOf(301, 302, 303, 307, 308)) {
                val location = connection.getHeaderField("Location") ?: return null
                connection.disconnect()
                connection = (URL(location).openConnection() as HttpURLConnection).apply {
                    connectTimeout = 30_000
                    readTimeout = 60_000
                    instanceFollowRedirects = true
                    setRequestProperty("User-Agent", "AtlasSight/1.0")
                }
                redirects++
            } else {
                break
            }
        }
        return connection
    }

    /**
     * Extract a .tar.bz2 archive, flattening the top-level directory so files
     * end up directly inside [targetDir] rather than nested.
     */
    private fun extractTarBz2(tarBz2File: File, targetDir: File) {
        var extractedCount = 0
        var skippedCount = 0
        FileInputStream(tarBz2File).use { fis ->
            BufferedInputStream(fis).use { bis ->
                BZip2CompressorInputStream(bis).use { bzIn ->
                    TarArchiveInputStream(bzIn).use { tarIn ->
                        var entry = tarIn.nextEntry
                        while (entry != null) {
                            // Strip the top-level directory from the path
                            val entryName = entry.name
                            val stripped = entryName.substringAfter('/', entryName)
                            if (stripped.isEmpty() || stripped == entryName.trimEnd('/')) {
                                // Top-level dir entry itself — skip
                                if (entry.isDirectory && '/' !in entryName.trimEnd('/')) {
                                    Log.d(TAG, "Skipping top-level dir: $entryName")
                                    skippedCount++
                                    entry = tarIn.nextEntry
                                    continue
                                }
                            }

                            val outputName = if ('/' in entryName) stripped else entryName
                            if (outputName.isBlank()) {
                                skippedCount++
                                entry = tarIn.nextEntry
                                continue
                            }

                            val outputFile = File(targetDir, outputName)

                            // Guard against zip-slip
                            if (!outputFile.canonicalPath.startsWith(targetDir.canonicalPath)) {
                                Log.w(TAG, "Zip-slip blocked: $entryName")
                                skippedCount++
                                entry = tarIn.nextEntry
                                continue
                            }

                            if (entry.isDirectory) {
                                outputFile.mkdirs()
                                Log.d(TAG, "  mkdir: $outputName")
                            } else {
                                outputFile.parentFile?.mkdirs()
                                FileOutputStream(outputFile).use { fos ->
                                    tarIn.copyTo(fos, 65536)
                                }
                                Log.d(TAG, "  extract: $outputName (${outputFile.length()} bytes)")
                                extractedCount++
                            }

                            entry = tarIn.nextEntry
                        }
                    }
                }
            }
        }
        Log.i(TAG, "Extracted ${tarBz2File.name}: $extractedCount files, $skippedCount skipped")

        // Log final directory contents for verification
        val finalContents = targetDir.walkTopDown().filter { it.isFile }.map {
            val rel = it.relativeTo(targetDir).path
            "$rel (${it.length()} bytes)"
        }.toList()
        Log.i(TAG, "Final contents of ${targetDir.name}/: $finalContents")
    }
}
