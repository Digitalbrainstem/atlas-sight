package dev.atlascortex.sight.vlm

/**
 * JNI wrapper for llama.cpp multimodal (mtmd) vision inference.
 *
 * Loads a Qwen3-VL GGUF that contains both the LLM and vision encoder,
 * then runs image + text → text inference entirely on-device.
 */
class VisionInferenceEngine {

    companion object {
        private var libraryLoaded = false

        @Synchronized
        fun ensureLoaded() {
            if (!libraryLoaded) {
                System.loadLibrary("atlas-sight-vlm")
                libraryLoaded = true
            }
        }
    }

    // ---- Native methods (implemented in vision_chat.cpp) ------------------

    private external fun nativeInit(nativeLibDir: String)
    private external fun nativeLoadModel(modelPath: String, nThreads: Int): Boolean
    private external fun nativeInfer(jpegBytes: ByteArray, prompt: String, maxTokens: Int): String
    private external fun nativeRelease()

    // ---- Public API -------------------------------------------------------

    private var modelLoaded = false

    /** Initialise llama backends.  Call once before [loadModel]. */
    fun init(nativeLibDir: String) {
        ensureLoaded()
        nativeInit(nativeLibDir)
    }

    /**
     * Load a GGUF model with embedded vision encoder.
     * @param modelPath absolute path to the .gguf file on device storage.
     * @param nThreads  number of CPU threads for inference (2–4 recommended).
     * @return true if the model (and its vision encoder) loaded successfully.
     */
    fun loadModel(modelPath: String, nThreads: Int = 4): Boolean {
        modelLoaded = nativeLoadModel(modelPath, nThreads)
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
        if (!modelLoaded) return ""
        return nativeInfer(jpegBytes, prompt, maxTokens)
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
