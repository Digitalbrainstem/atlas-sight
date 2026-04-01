/**
 * Atlas Sight — VLM JNI Bridge
 *
 * Wraps llama.cpp multimodal (mtmd) API for on-device vision-language
 * inference.  Accepts JPEG bytes + text prompt, returns generated text.
 *
 * Model: Qwen3-VL-2B-Instruct (Q4_K_M GGUF with embedded mmproj).
 */

#include <android/log.h>
#include <jni.h>
#include <string>
#include <vector>
#include <sstream>
#include <unistd.h>

#include "logging.h"
#include "llama.h"
#include "common.h"
#include "sampling.h"
#include "chat.h"
#include "mtmd.h"
#include "mtmd-helper.h"

// ---------------------------------------------------------------------------
// Global state (single model loaded at a time)
// ---------------------------------------------------------------------------

static llama_model                * g_model       = nullptr;
static llama_context              * g_context     = nullptr;
static mtmd_context               * g_mtmd_ctx    = nullptr;
static common_chat_templates_ptr    g_chat_tmpl;
static int                          g_n_threads   = 4;

static constexpr int   CONTEXT_SIZE   = 8192;
static constexpr int   BATCH_SIZE     = 2048;
static constexpr float SAMPLER_TEMP   = 0.1f; // low temp for factual descriptions

static const char * SYSTEM_PROMPT =
    "You are a vision assistant for a blind person. "
    "Describe scenes concisely and accurately. Focus on obstacles, people, "
    "objects, their positions, approximate distances, and any visible text. "
    "Prioritize safety-relevant information first.";

// ---------------------------------------------------------------------------
// UTF-8 validation (from llama.android ai_chat.cpp)
// ---------------------------------------------------------------------------

static bool is_valid_utf8(const char * s) {
    if (!s) return true;
    const auto * b = (const unsigned char *)s;
    int num;
    while (*b) {
        if      ((*b & 0x80) == 0x00) num = 1;
        else if ((*b & 0xE0) == 0xC0) num = 2;
        else if ((*b & 0xF0) == 0xE0) num = 3;
        else if ((*b & 0xF8) == 0xF0) num = 4;
        else return false;
        b++;
        for (int i = 1; i < num; i++) {
            if ((*b & 0xC0) != 0x80) return false;
            b++;
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// JNI: nativeInit — load backends and initialize llama
// ---------------------------------------------------------------------------

extern "C" JNIEXPORT void JNICALL
Java_dev_atlascortex_sight_vlm_VisionInferenceEngine_nativeInit(
        JNIEnv * env, jobject /*unused*/, jstring jNativeLibDir) {

    llama_log_set(vlm_android_log_callback, nullptr);
    mtmd_helper_log_set(vlm_android_log_callback, nullptr);

    const char * path = env->GetStringUTFChars(jNativeLibDir, nullptr);
    LOGi("Loading backends from %s", path);
    ggml_backend_load_all_from_path(path);
    env->ReleaseStringUTFChars(jNativeLibDir, path);

    llama_backend_init();
    LOGi("Backend initialised");
}

// ---------------------------------------------------------------------------
// JNI: nativeLoadModel — load GGUF (LLM + embedded mmproj)
// ---------------------------------------------------------------------------

extern "C" JNIEXPORT jboolean JNICALL
Java_dev_atlascortex_sight_vlm_VisionInferenceEngine_nativeLoadModel(
        JNIEnv * env, jobject /*unused*/, jstring jModelPath,
        jstring jMmprojPath, jint nThreads) {

    g_n_threads = (nThreads > 0) ? (int)nThreads : 4;

    const char * modelPath  = env->GetStringUTFChars(jModelPath, nullptr);
    const char * mmprojPath = env->GetStringUTFChars(jMmprojPath, nullptr);
    LOGi("Loading model from %s  mmproj from %s  (threads=%d)",
         modelPath, mmprojPath, g_n_threads);

    // --- Load text model ---------------------------------------------------
    llama_model_params mparams = llama_model_default_params();
    g_model = llama_model_load_from_file(modelPath, mparams);
    if (!g_model) {
        LOGe("Failed to load llama model");
        env->ReleaseStringUTFChars(jModelPath, modelPath);
        env->ReleaseStringUTFChars(jMmprojPath, mmprojPath);
        return JNI_FALSE;
    }

    // --- Create llama context ----------------------------------------------
    llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx           = CONTEXT_SIZE;
    cparams.n_batch         = BATCH_SIZE;
    cparams.n_ubatch        = BATCH_SIZE;
    cparams.n_threads       = g_n_threads;
    cparams.n_threads_batch = g_n_threads;

    g_context = llama_init_from_model(g_model, cparams);
    if (!g_context) {
        LOGe("Failed to create llama context");
        llama_model_free(g_model); g_model = nullptr;
        env->ReleaseStringUTFChars(jModelPath, modelPath);
        env->ReleaseStringUTFChars(jMmprojPath, mmprojPath);
        return JNI_FALSE;
    }

    // --- Create multimodal (vision) context from mmproj --------------------
    mtmd_context_params mctx = mtmd_context_params_default();
    mctx.use_gpu       = false;   // CPU-only on most Android devices
    mctx.print_timings = true;
    mctx.n_threads     = g_n_threads;
    mctx.warmup        = false;   // skip warmup to speed up load

    g_mtmd_ctx = mtmd_init_from_file(mmprojPath, g_model, mctx);
    env->ReleaseStringUTFChars(jModelPath, modelPath);
    env->ReleaseStringUTFChars(jMmprojPath, mmprojPath);

    if (!g_mtmd_ctx) {
        LOGe("Failed to create mtmd context — vision disabled");
        llama_free(g_context);      g_context = nullptr;
        llama_model_free(g_model);  g_model   = nullptr;
        return JNI_FALSE;
    }

    if (!mtmd_support_vision(g_mtmd_ctx)) {
        LOGw("Model reports no vision support");
    }

    // --- Chat template (Qwen-style) ---------------------------------------
    g_chat_tmpl = common_chat_templates_init(g_model, "");

    LOGi("Model loaded successfully  vision=%d",
         mtmd_support_vision(g_mtmd_ctx));
    return JNI_TRUE;
}

// ---------------------------------------------------------------------------
// JNI: nativeInfer — image + prompt → generated text
// ---------------------------------------------------------------------------

extern "C" JNIEXPORT jstring JNICALL
Java_dev_atlascortex_sight_vlm_VisionInferenceEngine_nativeInfer(
        JNIEnv * env, jobject /*unused*/,
        jbyteArray jJpegBytes, jstring jPrompt, jint maxTokens) {

    if (!g_model || !g_context || !g_mtmd_ctx) {
        LOGe("nativeInfer called but model not loaded");
        return env->NewStringUTF("");
    }

    // --- Decode JPEG into mtmd bitmap --------------------------------------
    jsize jpegLen   = env->GetArrayLength(jJpegBytes);
    jbyte * jpegBuf = env->GetByteArrayElements(jJpegBytes, nullptr);

    mtmd_bitmap * bitmap = mtmd_helper_bitmap_init_from_buf(
            g_mtmd_ctx,
            reinterpret_cast<const unsigned char *>(jpegBuf),
            static_cast<size_t>(jpegLen));
    env->ReleaseByteArrayElements(jJpegBytes, jpegBuf, JNI_ABORT);

    if (!bitmap) {
        LOGe("Failed to decode JPEG to bitmap");
        return env->NewStringUTF("");
    }

    // --- Build the chat-formatted prompt with media marker -----------------
    const char * userPrompt = env->GetStringUTFChars(jPrompt, nullptr);

    // User content: <__media__>\n<prompt>
    std::string userContent =
        std::string(mtmd_default_marker()) + "\n" + userPrompt;
    env->ReleaseStringUTFChars(jPrompt, userPrompt);

    // Format through chat template (system + user → assistant prefix)
    std::vector<common_chat_msg> history;
    std::string fullPrompt;

    const bool hasTmpl =
        common_chat_templates_was_explicit(g_chat_tmpl.get());

    if (hasTmpl) {
        common_chat_msg sysMsg;
        sysMsg.role    = "system";
        sysMsg.content = SYSTEM_PROMPT;
        std::string fmtSys = common_chat_format_single(
                g_chat_tmpl.get(), history, sysMsg, false, false);
        history.push_back(sysMsg);

        common_chat_msg usrMsg;
        usrMsg.role    = "user";
        usrMsg.content = userContent;
        std::string fmtUsr = common_chat_format_single(
                g_chat_tmpl.get(), history, usrMsg, true, false);
        history.push_back(usrMsg);

        fullPrompt = fmtSys + fmtUsr;
    } else {
        // Fallback: raw prompt with marker
        fullPrompt = userContent;
    }

    LOGd("Full prompt (%zu chars): %.120s…", fullPrompt.size(),
         fullPrompt.c_str());

    // --- Tokenize (text + image → chunks) ----------------------------------
    mtmd_input_text inputText;
    inputText.text          = fullPrompt.c_str();
    inputText.add_special   = true;
    inputText.parse_special = true;

    mtmd_input_chunks * chunks = mtmd_input_chunks_init();
    const mtmd_bitmap * bitmapArr[] = { bitmap };

    int32_t tokRes = mtmd_tokenize(
            g_mtmd_ctx, chunks, &inputText, bitmapArr, 1);
    mtmd_bitmap_free(bitmap);

    if (tokRes != 0) {
        LOGe("mtmd_tokenize failed: %d", tokRes);
        mtmd_input_chunks_free(chunks);
        return env->NewStringUTF("");
    }

    size_t totalInputTokens = mtmd_helper_get_n_tokens(chunks);
    LOGi("Input tokenised: %zu tokens across %zu chunks",
         totalInputTokens, mtmd_input_chunks_size(chunks));

    if ((int)totalInputTokens >= CONTEXT_SIZE - 4) {
        LOGe("Input too large for context (%zu >= %d)",
             totalInputTokens, CONTEXT_SIZE);
        mtmd_input_chunks_free(chunks);
        return env->NewStringUTF("");
    }

    // --- Clear KV cache for fresh single-turn inference --------------------
    llama_memory_clear(llama_get_memory(g_context), false);

    // --- Evaluate all chunks (text + encoded image embeddings) -------------
    llama_pos n_past = 0;
    int32_t evalRes = mtmd_helper_eval_chunks(
            g_mtmd_ctx, g_context, chunks,
            /* n_past    */ n_past,
            /* seq_id    */ 0,
            /* n_batch   */ BATCH_SIZE,
            /* logits_last */ true,
            /* new_n_past  */ &n_past);
    mtmd_input_chunks_free(chunks);

    if (evalRes != 0) {
        LOGe("mtmd_helper_eval_chunks failed: %d", evalRes);
        return env->NewStringUTF("");
    }

    LOGi("Chunks evaluated, n_past=%d — starting generation", (int)n_past);

    // --- Create sampler ----------------------------------------------------
    common_params_sampling sparams;
    sparams.temp = SAMPLER_TEMP;
    common_sampler * sampler = common_sampler_init(g_model, sparams);
    if (!sampler) {
        LOGe("Failed to create sampler");
        return env->NewStringUTF("");
    }

    // --- Token generation loop ---------------------------------------------
    const int maxTok = (maxTokens > 0) ? (int)maxTokens : 256;
    const auto * vocab = llama_model_get_vocab(g_model);
    std::string output;
    std::string pending_utf8;
    int generated = 0;

    llama_batch batch = llama_batch_init(1, 0, 1);

    while (generated < maxTok) {
        llama_token tok = common_sampler_sample(sampler, g_context, -1);
        common_sampler_accept(sampler, tok, true);

        if (llama_vocab_is_eog(vocab, tok)) {
            LOGd("EOS after %d tokens", generated);
            break;
        }

        std::string piece = common_token_to_piece(g_context, tok);
        pending_utf8 += piece;

        if (is_valid_utf8(pending_utf8.c_str())) {
            output += pending_utf8;
            pending_utf8.clear();
        }

        // Decode the token for next iteration
        common_batch_clear(batch);
        common_batch_add(batch, tok, n_past++, {0}, true);
        if (llama_decode(g_context, batch) != 0) {
            LOGe("llama_decode failed at token %d", generated);
            break;
        }
        generated++;
    }

    // Flush any remaining bytes
    if (!pending_utf8.empty() && is_valid_utf8(pending_utf8.c_str())) {
        output += pending_utf8;
    }

    llama_batch_free(batch);
    common_sampler_free(sampler);

    LOGi("Generated %d tokens (%zu bytes)", generated, output.size());
    return env->NewStringUTF(output.c_str());
}

// ---------------------------------------------------------------------------
// JNI: nativeRelease — free all resources
// ---------------------------------------------------------------------------

extern "C" JNIEXPORT void JNICALL
Java_dev_atlascortex_sight_vlm_VisionInferenceEngine_nativeRelease(
        JNIEnv * /*env*/, jobject /*unused*/) {

    LOGi("Releasing VLM resources");
    g_chat_tmpl.reset();
    if (g_mtmd_ctx) { mtmd_free(g_mtmd_ctx);       g_mtmd_ctx = nullptr; }
    if (g_context)  { llama_free(g_context);        g_context  = nullptr; }
    if (g_model)    { llama_model_free(g_model);    g_model    = nullptr; }
    llama_backend_free();
}
