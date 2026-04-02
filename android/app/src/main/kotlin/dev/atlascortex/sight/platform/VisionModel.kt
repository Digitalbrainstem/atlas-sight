package dev.atlascortex.sight.platform

import android.content.Context
import android.util.Log
import dev.atlascortex.sight.core.*
import dev.atlascortex.sight.vlm.VisionInferenceEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Qwen3-VL-2B via llama.cpp (mtmd) — on-device vision-language model.
 * Handles scene description, object detection, and OCR through real
 * multimodal inference (image + text → text).
 */
class VisionModel(private val context: Context) {

    companion object {
        private const val TAG = "VisionModel"
    }

    private val engine = VisionInferenceEngine()
    private var isLoaded = false
    private val modelDir: File get() = File(context.filesDir, "models/qwen3-vl")

    // Serialize all native VLM calls — C++ global state is NOT thread-safe
    private val inferenceMutex = Mutex()

    fun isReady(): Boolean = isLoaded

    suspend fun load(): Boolean = withContext(Dispatchers.IO) {
        try {
            Log.i(TAG, "load() — checking model files in ${modelDir.absolutePath}")
            if (!modelDir.exists()) {
                Log.e(TAG, "Model directory does not exist: ${modelDir.absolutePath}")
                return@withContext false
            }

            val contents = modelDir.listFiles()?.map { "${it.name} (${it.length() / 1_000_000}MB)" }
            Log.i(TAG, "Model directory contents: $contents")

            val modelFile = File(modelDir, "Qwen3-VL-2B-Instruct-Q4_K_M.gguf")
            val mmprojFile = File(modelDir, "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf")
            if (!modelFile.exists()) {
                Log.e(TAG, "LLM model not found: ${modelFile.absolutePath}")
                return@withContext false
            }
            if (!mmprojFile.exists()) {
                Log.e(TAG, "Vision encoder not found: ${mmprojFile.absolutePath}")
                return@withContext false
            }
            Log.i(TAG, "LLM: ${modelFile.length() / 1_000_000}MB, mmproj: ${mmprojFile.length() / 1_000_000}MB")

            val nativeLibDir = context.applicationInfo.nativeLibraryDir
            Log.i(TAG, "Initializing native engine from $nativeLibDir")
            engine.init(nativeLibDir)
            Log.i(TAG, "Native engine initialized")

            val nThreads = (Runtime.getRuntime().availableProcessors() - 2).coerceIn(2, 4)
            Log.i(TAG, "Loading model with $nThreads threads (available CPUs: ${Runtime.getRuntime().availableProcessors()})…")
            val startTime = System.currentTimeMillis()
            isLoaded = engine.loadModel(modelFile.absolutePath, mmprojFile.absolutePath, nThreads)
            val elapsed = System.currentTimeMillis() - startTime
            Log.i(TAG, "Model load result: $isLoaded (took ${elapsed}ms)")
            isLoaded
        } catch (e: Exception) {
            Log.e(TAG, "Model load failed with exception: ${e.message}", e)
            isLoaded = false
            false
        } catch (e: UnsatisfiedLinkError) {
            Log.e(TAG, "Native library not found: ${e.message}", e)
            isLoaded = false
            false
        }
    }

    /** Describe the scene in the image with the given verbosity. */
    suspend fun describeScene(
        jpegBytes: ByteArray,
        verbosity: Verbosity = Verbosity.NORMAL,
    ): SceneDescription = withContext(Dispatchers.Default) {
        val prompt = when (verbosity) {
            Verbosity.BRIEF -> "Briefly describe what you see in one sentence."
            Verbosity.NORMAL -> "Describe what you see, including any people, objects, and obstacles."
            Verbosity.DETAILED -> "Describe in detail everything you see including positions, distances, colors, and any text visible."
        }
        val maxTokens = when (verbosity) {
            Verbosity.BRIEF -> 64
            Verbosity.NORMAL -> 192
            Verbosity.DETAILED -> 384
        }
        Log.d(TAG, "describeScene: verbosity=$verbosity maxTokens=$maxTokens jpeg=${jpegBytes.size} bytes")
        val startTime = System.currentTimeMillis()
        val result = inferenceMutex.withLock {
            engine.describeImage(jpegBytes, prompt, maxTokens)
        }
        val elapsed = System.currentTimeMillis() - startTime
        Log.i(TAG, "describeScene: ${result.length} chars in ${elapsed}ms")
        if (result.isBlank()) {
            Log.w(TAG, "describeScene: VLM returned empty result")
        }
        val objects = extractObjects(result)
        SceneDescription(
            text = result.ifBlank { "Unable to process the image right now." },
            objects = objects,
            verbosity = verbosity,
        )
    }

    /** Detect objects in the image. */
    suspend fun detectObjects(jpegBytes: ByteArray): List<DetectedObject> =
        withContext(Dispatchers.Default) {
            val prompt = "List every object you can see with its position. Format: object_name (position)"
            Log.d(TAG, "detectObjects: jpeg=${jpegBytes.size} bytes")
            val startTime = System.currentTimeMillis()
            val result = inferenceMutex.withLock {
                engine.describeImage(jpegBytes, prompt, 256)
            }
            val elapsed = System.currentTimeMillis() - startTime
            Log.d(TAG, "detectObjects: ${result.length} chars in ${elapsed}ms")
            extractObjects(result)
        }

    /** Read text from the image (OCR). */
    suspend fun readText(jpegBytes: ByteArray): String = withContext(Dispatchers.Default) {
        val prompt = "Read all visible text in this image, in natural reading order (top to bottom, left to right). Only output the text content."
        Log.d(TAG, "readText: jpeg=${jpegBytes.size} bytes")
        val startTime = System.currentTimeMillis()
        val result = inferenceMutex.withLock {
            engine.describeImage(jpegBytes, prompt, 384)
        }
        val elapsed = System.currentTimeMillis() - startTime
        Log.i(TAG, "readText: ${result.length} chars in ${elapsed}ms")
        result
    }

    /** Answer a follow-up question about the image. */
    suspend fun askAboutImage(jpegBytes: ByteArray, question: String): String =
        withContext(Dispatchers.Default) {
            Log.d(TAG, "askAboutImage: jpeg=${jpegBytes.size} bytes, question='$question'")
            val startTime = System.currentTimeMillis()
            val result = inferenceMutex.withLock {
                engine.describeImage(jpegBytes, question, 256)
            }
            val elapsed = System.currentTimeMillis() - startTime
            Log.d(TAG, "askAboutImage: ${result.length} chars in ${elapsed}ms")
            result
        }

    fun release() {
        engine.release()
        isLoaded = false
    }

    // --- Object extraction from VLM output ---------------------------------

    private fun extractObjects(text: String): List<DetectedObject> {
        val categories = mapOf(
            "person" to ObjectCategory.PERSON, "people" to ObjectCategory.PERSON, "man" to ObjectCategory.PERSON, "woman" to ObjectCategory.PERSON, "child" to ObjectCategory.PERSON,
            "car" to ObjectCategory.VEHICLE, "truck" to ObjectCategory.VEHICLE, "bus" to ObjectCategory.VEHICLE, "bicycle" to ObjectCategory.VEHICLE, "motorcycle" to ObjectCategory.VEHICLE,
            "chair" to ObjectCategory.FURNITURE, "table" to ObjectCategory.FURNITURE, "desk" to ObjectCategory.FURNITURE, "couch" to ObjectCategory.FURNITURE, "bench" to ObjectCategory.FURNITURE,
            "door" to ObjectCategory.DOOR, "gate" to ObjectCategory.DOOR, "entrance" to ObjectCategory.DOOR,
            "stairs" to ObjectCategory.STAIRS, "steps" to ObjectCategory.STAIRS, "staircase" to ObjectCategory.STAIRS,
            "wall" to ObjectCategory.OBSTACLE, "pole" to ObjectCategory.OBSTACLE, "fence" to ObjectCategory.OBSTACLE, "barrier" to ObjectCategory.OBSTACLE, "cone" to ObjectCategory.OBSTACLE,
            "sign" to ObjectCategory.SIGN, "traffic light" to ObjectCategory.SIGN, "stop sign" to ObjectCategory.SIGN,
            "dog" to ObjectCategory.ANIMAL, "cat" to ObjectCategory.ANIMAL, "bird" to ObjectCategory.ANIMAL,
            "food" to ObjectCategory.FOOD, "plate" to ObjectCategory.FOOD, "cup" to ObjectCategory.FOOD, "bottle" to ObjectCategory.FOOD,
            "phone" to ObjectCategory.ELECTRONIC, "laptop" to ObjectCategory.ELECTRONIC, "screen" to ObjectCategory.ELECTRONIC, "monitor" to ObjectCategory.ELECTRONIC,
        )
        val found = mutableListOf<DetectedObject>()
        val lower = text.lowercase()
        for ((word, category) in categories) {
            if (word in lower) {
                found.add(DetectedObject(word, category, 0.7f))
            }
        }
        return found.distinctBy { it.label }
    }
}
