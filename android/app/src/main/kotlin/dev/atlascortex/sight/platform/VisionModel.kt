package dev.atlascortex.sight.platform

import android.content.Context
import dev.atlascortex.sight.core.*
import dev.atlascortex.sight.vlm.VisionInferenceEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Qwen3-VL-2B via llama.cpp (mtmd) — on-device vision-language model.
 * Handles scene description, object detection, and OCR through real
 * multimodal inference (image + text → text).
 */
class VisionModel(private val context: Context) {

    private val engine = VisionInferenceEngine()
    private var isLoaded = false
    private val modelDir: File get() = File(context.filesDir, "models/qwen3-vl")

    fun isReady(): Boolean = isLoaded

    suspend fun load(): Boolean = withContext(Dispatchers.IO) {
        try {
            val modelFile = File(modelDir, "Qwen3-VL-2B-Instruct-Q4_K_M.gguf")
            val mmprojFile = File(modelDir, "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf")
            if (!modelFile.exists()) {
                android.util.Log.e("VisionModel", "LLM model not found: ${modelFile.absolutePath}")
                return@withContext false
            }
            if (!mmprojFile.exists()) {
                android.util.Log.e("VisionModel", "Vision encoder not found: ${mmprojFile.absolutePath}")
                return@withContext false
            }
            android.util.Log.i("VisionModel", "LLM: ${modelFile.length() / 1_000_000}MB, mmproj: ${mmprojFile.length() / 1_000_000}MB")

            val nativeLibDir = context.applicationInfo.nativeLibraryDir
            engine.init(nativeLibDir)

            val nThreads = (Runtime.getRuntime().availableProcessors() - 2).coerceIn(2, 4)
            android.util.Log.i("VisionModel", "Loading model with $nThreads threads...")
            isLoaded = engine.loadModel(modelFile.absolutePath, mmprojFile.absolutePath, nThreads)
            android.util.Log.i("VisionModel", "Model load result: $isLoaded")
            isLoaded
        } catch (e: Exception) {
            android.util.Log.e("VisionModel", "Model load failed: ${e.message}", e)
            isLoaded = false
            false
        } catch (e: UnsatisfiedLinkError) {
            android.util.Log.e("VisionModel", "Native library not found: ${e.message}", e)
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
        val result = engine.describeImage(jpegBytes, prompt, maxTokens)
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
            val result = engine.describeImage(jpegBytes, prompt, 256)
            extractObjects(result)
        }

    /** Read text from the image (OCR). */
    suspend fun readText(jpegBytes: ByteArray): String = withContext(Dispatchers.Default) {
        val prompt = "Read all visible text in this image, in natural reading order (top to bottom, left to right). Only output the text content."
        engine.describeImage(jpegBytes, prompt, 384)
    }

    /** Answer a follow-up question about the image. */
    suspend fun askAboutImage(jpegBytes: ByteArray, question: String): String =
        withContext(Dispatchers.Default) {
            engine.describeImage(jpegBytes, question, 256)
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
