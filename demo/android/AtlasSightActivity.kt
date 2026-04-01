package com.example.llama

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.util.Log
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.arm.aichat.AiChat
import com.arm.aichat.InferenceEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.onCompletion
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.math.abs

/**
 * Atlas Sight — AI Vision Assistant Activity
 *
 * Full-screen camera with accessibility gestures for visually impaired users.
 * Uses on-device LLM (via llama.cpp JNI), offline STT, and offline TTS.
 *
 * Gestures:
 *   Double-tap → capture frame, describe scene
 *   Long press → voice question
 *   Swipe right → "read text" mode
 *   Swipe left → repeat last description
 *   Swipe up → increase speech rate
 *   Swipe down → decrease speech rate
 *   Shake → "where am I?" emergency
 */
class AtlasSightActivity : AppCompatActivity(),
    TextToSpeech.OnInitListener,
    SensorEventListener {

    companion object {
        private const val TAG = "AtlasSight"
        private const val REQUEST_PERMISSIONS = 100
        private val REQUIRED_PERMISSIONS = arrayOf(
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO,
        )
        private const val SHAKE_THRESHOLD = 25f
        private const val SHAKE_COOLDOWN_MS = 3000L
        private const val SYSTEM_PROMPT =
            "You are Atlas Sight, a concise AI assistant helping a visually impaired person. " +
            "Always respond in 2-3 short sentences suitable for being read aloud. " +
            "Be warm, specific, and helpful."
    }

    // UI
    private lateinit var cameraPreview: PreviewView
    private lateinit var statusDot: View
    private lateinit var statusText: TextView
    private lateinit var descriptionText: TextView
    private lateinit var modeBadge: TextView
    private lateinit var touchOverlay: View

    // Camera
    private var imageCapture: ImageCapture? = null
    private lateinit var cameraExecutor: ExecutorService

    // LLM
    private lateinit var engine: InferenceEngine
    private var modelReady = false

    // TTS
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var speechRate = 1.0f

    // STT
    private var speechRecognizer: SpeechRecognizer? = null
    private var isListening = false

    // Sensors
    private var sensorManager: SensorManager? = null
    private var lastShakeTime = 0L

    // Haptics
    private var vibrator: Vibrator? = null

    // State
    private var lastDescription = ""
    private var lastImageContext = ""
    private var currentMode = "describe" // describe | read_text | emergency
    private var busy = false

    // -----------------------------------------------------------------------
    // Lifecycle
    // -----------------------------------------------------------------------

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Full screen immersive
        window.statusBarColor = Color.BLACK
        window.navigationBarColor = Color.BLACK

        setContentView(R.layout.sight_layout)

        // Bind views
        cameraPreview = findViewById(R.id.camera_preview)
        statusDot = findViewById(R.id.status_dot)
        statusText = findViewById(R.id.status_text)
        descriptionText = findViewById(R.id.description_text)
        modeBadge = findViewById(R.id.mode_badge)
        touchOverlay = findViewById(R.id.touch_overlay)

        cameraExecutor = Executors.newSingleThreadExecutor()

        // Initialize subsystems
        initHaptics()
        initTTS()
        initShakeDetection()
        initGestures()

        // Check permissions, then start camera + LLM
        if (allPermissionsGranted()) {
            startCamera()
            initLLM()
        } else {
            ActivityCompat.requestPermissions(this, REQUIRED_PERMISSIONS, REQUEST_PERMISSIONS)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
        tts?.shutdown()
        speechRecognizer?.destroy()
        sensorManager?.unregisterListener(this)
        if (modelReady) {
            engine.destroy()
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_PERMISSIONS) {
            if (allPermissionsGranted()) {
                startCamera()
                initLLM()
            } else {
                speak("Camera and microphone permissions are required for Atlas Sight.")
                setStatus("error", "Permissions needed")
            }
        }
    }

    private fun allPermissionsGranted() = REQUIRED_PERMISSIONS.all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    // -----------------------------------------------------------------------
    // Camera (CameraX)
    // -----------------------------------------------------------------------

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.surfaceProvider = cameraPreview.surfaceProvider
            }

            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .build()

            val cameraSelector = CameraSelector.Builder()
                .requireLensFacing(CameraSelector.LENS_FACING_BACK)
                .build()

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(this, cameraSelector, preview, imageCapture)
                Log.i(TAG, "Camera started")
            } catch (e: Exception) {
                Log.e(TAG, "Camera failed to start", e)
                setStatus("error", "Camera failed")
            }
        }, ContextCompat.getMainExecutor(this))
    }

    /** Capture current camera frame as a Bitmap. */
    private fun captureFrame(): Bitmap? {
        return cameraPreview.bitmap
    }

    // -----------------------------------------------------------------------
    // LLM (llama.cpp via JNI)
    // -----------------------------------------------------------------------

    private fun initLLM() {
        setStatus("busy", "Loading AI model…")

        engine = AiChat.getInferenceEngine(this)

        lifecycleScope.launch {
            val modelPath = findModelFile()
            if (modelPath == null) {
                setStatus("error", "No model found")
                speak(
                    "No AI model found on this device. " +
                    "Please copy a G-G-U-F model file to the Downloads folder."
                )
                return@launch
            }

            Log.i(TAG, "Loading model: $modelPath")
            try {
                engine.loadModel(modelPath)
                engine.setSystemPrompt(SYSTEM_PROMPT)
                modelReady = true
                setStatus("ready", "Ready — double-tap to describe")
                speak(
                    "Atlas Sight ready. Everything is running on your phone. " +
                    "Double-tap anywhere to describe what you see. " +
                    "Long press to ask a question."
                )
            } catch (e: Exception) {
                Log.e(TAG, "Model load failed", e)
                setStatus("error", "Model load failed")
                speak("Failed to load the AI model. Check that the model file is valid.")
            }
        }
    }

    /** Search common locations for a .gguf model file. */
    private suspend fun findModelFile(): String? = withContext(Dispatchers.IO) {
        val searchDirs = listOf(
            File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).path),
            File(getExternalFilesDir(null), "models"),
            filesDir,
            File(Environment.getExternalStorageDirectory(), "atlas-sight/models"),
        )

        for (dir in searchDirs) {
            if (!dir.exists()) continue
            val gguf = dir.listFiles()?.filter { it.extension == "gguf" }?.firstOrNull()
            if (gguf != null) {
                Log.i(TAG, "Found model: ${gguf.absolutePath}")
                return@withContext gguf.absolutePath
            }
        }
        null
    }

    /** Send a prompt to the LLM and collect the response. */
    private fun generateResponse(prompt: String, onResult: (String) -> Unit) {
        if (!modelReady) {
            onResult("The AI model is still loading. Please wait.")
            return
        }

        lifecycleScope.launch {
            val result = StringBuilder()
            engine.sendUserPrompt(prompt, predictLength = 512)
                .catch { e ->
                    Log.e(TAG, "Generation error", e)
                    onResult("Sorry, something went wrong. Please try again.")
                }
                .onCompletion {
                    val text = stripThinkTags(result.toString().trim())
                    if (text.isNotBlank()) {
                        onResult(text)
                    } else {
                        onResult("I received your request but need a moment. Please try again.")
                    }
                }
                .collect { token ->
                    result.append(token)
                }
        }
    }

    /** Strip Qwen3 <think>...</think> blocks from output. */
    private fun stripThinkTags(text: String): String {
        if ("<think>" !in text) return text

        // Closed blocks: remove <think>...</think>, keep the rest
        val cleaned = text.replace(Regex("<think>.*?</think>\\s*", RegexOption.DOT_MATCHES_ALL), "").trim()
        if (cleaned.isNotBlank() && "<think>" !in cleaned) return cleaned

        // Unclosed block: model ran out of tokens mid-thought — return fallback
        return "I'm still processing. Please try again."
    }

    // -----------------------------------------------------------------------
    // TTS (Android TextToSpeech — offline)
    // -----------------------------------------------------------------------

    private fun initTTS() {
        tts = TextToSpeech(this, this)
    }

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            tts?.language = Locale.US
            tts?.setSpeechRate(speechRate)
            ttsReady = true
            Log.i(TAG, "TTS initialized")
        } else {
            Log.e(TAG, "TTS init failed: $status")
        }
    }

    private fun speak(text: String, onDone: (() -> Unit)? = null) {
        if (!ttsReady) {
            Log.w(TAG, "TTS not ready, skipping: $text")
            onDone?.invoke()
            return
        }

        tts?.stop()
        tts?.setSpeechRate(speechRate)

        if (onDone != null) {
            tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) {}
                override fun onDone(utteranceId: String?) {
                    runOnUiThread { onDone() }
                }
                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) {
                    runOnUiThread { onDone() }
                }
            })
        }

        tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "atlas_${System.currentTimeMillis()}")
    }

    private fun stopSpeech() {
        tts?.stop()
    }

    // -----------------------------------------------------------------------
    // STT (Android SpeechRecognizer — offline)
    // -----------------------------------------------------------------------

    private fun startListening() {
        if (isListening || busy) return

        stopSpeech()
        isListening = true
        vibrate(50)
        setStatus("listening", "Listening… speak now")

        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            speak("Speech recognition is not available on this device.")
            isListening = false
            return
        }

        speechRecognizer?.destroy()
        speechRecognizer = SpeechRecognizer.createSpeechRecognizer(this)

        speechRecognizer?.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {
                isListening = false
                setStatus("busy", "Processing…")
            }

            override fun onResults(results: Bundle?) {
                isListening = false
                val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                val transcript = matches?.firstOrNull()?.trim()

                if (transcript.isNullOrBlank()) {
                    setStatus("ready", "No speech detected")
                    speak("I didn't catch that. Try again.")
                    return
                }

                Log.i(TAG, "Heard: $transcript")
                setStatus("ready", "Heard: \"$transcript\"")
                vibrate(intArrayOf(0, 50, 50, 50))
                handleVoiceQuestion(transcript)
            }

            override fun onError(error: Int) {
                isListening = false
                val msg = when (error) {
                    SpeechRecognizer.ERROR_NO_MATCH -> "No speech detected"
                    SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Speech timeout"
                    SpeechRecognizer.ERROR_AUDIO -> "Audio error"
                    SpeechRecognizer.ERROR_NETWORK,
                    SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Network error — enable offline speech pack"
                    else -> "Speech error ($error)"
                }
                setStatus("ready", msg)
                if (error != SpeechRecognizer.ERROR_NO_MATCH) {
                    speak("$msg. Try again.")
                } else {
                    speak("I didn't hear anything. Try again.")
                }
            }

            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-US")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
        }

        speechRecognizer?.startListening(intent)
    }

    private fun stopListening() {
        if (isListening) {
            speechRecognizer?.stopListening()
            isListening = false
        }
    }

    // -----------------------------------------------------------------------
    // Gesture detection
    // -----------------------------------------------------------------------

    private fun initGestures() {
        val gestureDetector = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {

            override fun onDoubleTap(e: MotionEvent): Boolean {
                doCapture()
                return true
            }

            override fun onLongPress(e: MotionEvent) {
                startListening()
            }

            override fun onFling(
                e1: MotionEvent?, e2: MotionEvent,
                velocityX: Float, velocityY: Float
            ): Boolean {
                if (e1 == null) return false

                val dx = e2.x - e1.x
                val dy = e2.y - e1.y

                if (abs(dx) > abs(dy) * 1.5f && abs(dx) > 100) {
                    // Horizontal swipe
                    if (dx > 0) {
                        // Swipe right → read text mode
                        setMode("read_text")
                        vibrate(50)
                        speak("Read text mode. Double-tap to read text in view.")
                    } else {
                        // Swipe left → repeat
                        repeatLast()
                    }
                    return true
                }

                if (abs(dy) > abs(dx) * 1.5f && abs(dy) > 100) {
                    // Vertical swipe
                    if (dy < 0) {
                        // Swipe up → faster speech
                        speechRate = (speechRate + 0.25f).coerceAtMost(2.5f)
                        vibrate(30)
                        speak("Speed ${String.format("%.2f", speechRate)}")
                    } else {
                        // Swipe down → slower speech
                        speechRate = (speechRate - 0.25f).coerceAtLeast(0.5f)
                        vibrate(30)
                        speak("Speed ${String.format("%.2f", speechRate)}")
                    }
                    return true
                }

                return false
            }

            override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
                // Single tap: no-op (avoid accidental triggers)
                return true
            }
        })

        touchOverlay.setOnTouchListener { _, event ->
            gestureDetector.onTouchEvent(event)
            true
        }
    }

    // -----------------------------------------------------------------------
    // Shake detection
    // -----------------------------------------------------------------------

    private fun initShakeDetection() {
        sensorManager = getSystemService(SENSOR_SERVICE) as? SensorManager
        val accelerometer = sensorManager?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        accelerometer?.let {
            sensorManager?.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        }
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event?.sensor?.type != Sensor.TYPE_ACCELEROMETER) return

        val x = event.values[0]
        val y = event.values[1]
        val z = event.values[2]
        val total = abs(x) + abs(y) + abs(z)

        if (total > SHAKE_THRESHOLD) {
            val now = System.currentTimeMillis()
            if (now - lastShakeTime > SHAKE_COOLDOWN_MS) {
                lastShakeTime = now
                setMode("emergency")
                vibrate(intArrayOf(0, 100, 50, 100, 50, 100))
                speak("Emergency mode. Capturing surroundings.") {
                    doCapture()
                }
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    // -----------------------------------------------------------------------
    // Haptic feedback
    // -----------------------------------------------------------------------

    private fun initHaptics() {
        vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vm = getSystemService(VIBRATOR_MANAGER_SERVICE) as? VibratorManager
            vm?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            getSystemService(VIBRATOR_SERVICE) as? Vibrator
        }
    }

    private fun vibrate(durationMs: Long) {
        vibrator?.vibrate(VibrationEffect.createOneShot(durationMs, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    private fun vibrate(pattern: IntArray) {
        val timings = pattern.map { it.toLong() }.toLongArray()
        vibrator?.vibrate(VibrationEffect.createWaveform(timings, -1))
    }

    // -----------------------------------------------------------------------
    // Actions
    // -----------------------------------------------------------------------

    private fun doCapture() {
        if (busy || !modelReady) {
            if (!modelReady) speak("The AI model is still loading. Please wait.")
            return
        }
        busy = true

        vibrate(100)
        setStatus("busy", "Capturing…")

        val bitmap = captureFrame()
        if (bitmap == null) {
            setStatus("error", "Camera not ready")
            speak("Camera is not ready yet.")
            busy = false
            return
        }

        setStatus("busy", "Thinking…")
        speak("Analyzing")

        val imageKb = (bitmap.byteCount / 1024)
        val prompt = when (currentMode) {
            "read_text" ->
                "The user pointed their phone camera at something and wants you to read any " +
                "text visible. This is a demo without real vision — acknowledge their request " +
                "and explain that real text reading will work once a vision model is connected. " +
                "Be warm and brief."
            "emergency" ->
                "The user triggered 'where am I?' emergency mode. This is a demo — acknowledge " +
                "the request and explain that with real vision you would describe surroundings, " +
                "identify landmarks, and help orient them. Be reassuring and brief."
            else ->
                "The user captured an image (${imageKb}KB) with their phone camera. " +
                "This is a demo — real vision is not yet connected but the camera works. " +
                "Acknowledge the image and briefly describe what you WOULD do with real vision: " +
                "identify objects, read text, detect obstacles, describe spatial layout. " +
                "Be warm and concise (2-3 sentences)."
        }

        generateResponse(prompt) { description ->
            runOnUiThread {
                lastDescription = description
                lastImageContext = description
                descriptionText.text = description
                vibrate(intArrayOf(0, 50, 50, 50))
                setStatus("ready", "Done — double-tap for new capture")
                speak(description)
                busy = false
            }
        }
    }

    private fun handleVoiceQuestion(question: String) {
        if (busy) return
        busy = true

        setStatus("busy", "Thinking…")

        val contextPart = if (lastImageContext.isNotBlank()) {
            " The user previously saw: '$lastImageContext'."
        } else ""

        val prompt =
            "The user asks: \"$question\"$contextPart " +
            "Answer helpfully and concisely. If the question relates to something visual " +
            "and you don't have image data, say so honestly. " +
            "Keep your response under 3 sentences."

        generateResponse(prompt) { answer ->
            runOnUiThread {
                lastDescription = answer
                descriptionText.text = answer
                setStatus("ready", "Ready")
                speak(answer)
                busy = false
            }
        }
    }

    private fun repeatLast() {
        vibrate(50)
        if (lastDescription.isNotBlank()) {
            speak(lastDescription)
        } else {
            speak("Nothing to repeat yet. Double-tap to capture a scene first.")
        }
    }

    // -----------------------------------------------------------------------
    // UI helpers
    // -----------------------------------------------------------------------

    private fun setStatus(type: String, text: String) {
        runOnUiThread {
            statusText.text = text
            val color = when (type) {
                "error" -> Color.parseColor("#F44336")
                "busy" -> Color.parseColor("#FF9800")
                "listening" -> Color.parseColor("#2196F3")
                else -> Color.parseColor("#4CAF50")
            }
            statusDot.setBackgroundColor(color)
        }
    }

    private fun setMode(mode: String) {
        currentMode = mode
        val label = when (mode) {
            "read_text" -> "Read Text"
            "emergency" -> "Where Am I?"
            else -> "Atlas Sight"
        }
        runOnUiThread { modeBadge.text = label }
    }
}
