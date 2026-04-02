package dev.atlascortex.sight.vlm

/**
 * JNI wrapper for llama.cpp multimodal (mtmd) vision inference.
 *
 * Loads a Qwen3-VL GGUF that contains both the LLM and vision encoder,
 * then runs image + text → text inference entirely on-device.
 */
class VisionInferenceEngine {

    companion object {
        private const val TAG = "VisionInferenceEngine"
        private var libraryLoaded = false

        @Synchronized
        fun ensureLoaded() {
            if (!libraryLoaded) {
                android.util.Log.i(TAG, "Loading native library 'atlas-sight-vlm'…")
                System.loadLibrary("atlas-sight-vlm")
                libraryLoaded = true
                android.util.Log.i(TAG, "Native library loaded successfully")
            }
        }
    }

    // ---- Native methods (implemented in vision_chat.cpp) ------------------

    private external fun nativeInit(nativeLibDir: String)
    private external fun nativeLoadModel(modelPath: String, mmprojPath: String, nThreads: Int): Boolean
    private external fun nativeInfer(jpegBytes: ByteArray, prompt: String, maxTokens: Int): String
    private external fun nativeRelease()

    // ---- Public API -------------------------------------------------------

    private var modelLoaded = false

    /** Initialise llama backends.  Call once before [loadModel]. */
    fun init(nativeLibDir: String) {
        ensureLoaded()
        android.util.Log.i(TAG, "Calling nativeInit($nativeLibDir)")
        nativeInit(nativeLibDir)
        android.util.Log.i(TAG, "nativeInit complete")
    }

    /**
     * Load a GGUF model + separate vision encoder (mmproj).
     * @param modelPath   absolute path to the LLM .gguf file.
     * @param mmprojPath  absolute path to the mmproj .gguf file (vision encoder).
     * @param nThreads    number of CPU threads for inference (2–4 recommended).
     * @return true if both the LLM and vision encoder loaded successfully.
     */
    fun loadModel(modelPath: String, mmprojPath: String, nThreads: Int = 4): Boolean {
        android.util.Log.i(TAG, "Loading model: llm=$modelPath mmproj=$mmprojPath threads=$nThreads")
        modelLoaded = nativeLoadModel(modelPath, mmprojPath, nThreads)
        android.util.Log.i(TAG, "Model loaded: $modelLoaded")
        return modelLoaded
    }

    /**
     * Run vision-language inference.
     * @param jpegBytes raw JPEG image bytes (e.g. from CameraX).
     * @param prompt    text prompt describing what to do with the image.
     * @param maxTokens upper limit on generated tokens.
     * @return generated text, or empty string on failure.
     */
    fun describeImage(jpegBytes: ByteArray, prompt: String, maxTokens: Int = 256): String {
        if (!modelLoaded) {
            android.util.Log.w(TAG, "describeImage called but model not loaded")
            return ""
        }
        android.util.Log.d(TAG, "nativeInfer: jpeg=${jpegBytes.size} bytes, prompt=${prompt.take(60)}…, maxTokens=$maxTokens")
        val result = nativeInfer(jpegBytes, prompt, maxTokens)
        android.util.Log.d(TAG, "nativeInfer returned: ${result.length} chars")
        return result
    }

    /** Release all native resources.  The engine cannot be reused after this. */
    fun release() {
        if (modelLoaded) {
            nativeRelease()
            modelLoaded = false
        }
    }

    fun isReady(): Boolean = modelLoaded
}
