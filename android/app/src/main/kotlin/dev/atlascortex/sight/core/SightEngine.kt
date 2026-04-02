package dev.atlascortex.sight.core

import android.content.Context
import android.util.Log
import dev.atlascortex.sight.core.modes.*
import dev.atlascortex.sight.platform.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/**
 * Main orchestrator — binds all subsystems together.
 * Routes gestures/voice → modes → vision → speech/haptic/audio.
 */
class SightEngine(private val context: Context) {

    companion object {
        private const val TAG = "SightEngine"
    }

    // Core
    val config = Config(context)
    val commandParser = CommandParser()
    val contextTracker = ContextTracker()
    val obstacleWarner = ObstacleWarner()
    val audioCues = AudioCues()

    // Mode system
    val modeManager = ModeManager(config, contextTracker)
    val exploreMode = ExploreMode(config, obstacleWarner, contextTracker)
    val readMode = ReadMode(config)
    lateinit var navigateMode: NavigateMode
    val identifyMode = IdentifyMode(config)

    // Platform
    lateinit var cameraManager: CameraManager
    lateinit var visionModel: VisionModel
    lateinit var speechSynthesizer: SpeechSynthesizer
    lateinit var speechRecognizer: SpeechRecognizer
    lateinit var wakeWordDetector: WakeWordDetector
    lateinit var gestureHandler: GestureHandler
    lateinit var hapticEngine: HapticEngine
    lateinit var orientationHelper: OrientationHelper
    lateinit var permissions: Permissions

    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private var processingJob: Job? = null

    private val _statusText = MutableStateFlow("Initializing Atlas Sight…")
    val statusText: StateFlow<String> = _statusText.asStateFlow()

    private val _isReady = MutableStateFlow(false)
    val isReady: StateFlow<Boolean> = _isReady.asStateFlow()

    fun initialize() {
        // Platform components
        cameraManager = CameraManager(context)
        visionModel = VisionModel(context)
        speechSynthesizer = SpeechSynthesizer(context)
        speechRecognizer = SpeechRecognizer(context)
        wakeWordDetector = WakeWordDetector(context)
        gestureHandler = GestureHandler(context)
        hapticEngine = HapticEngine(context)
        orientationHelper = OrientationHelper(context)
        permissions = Permissions(context)

        // Mode with orientation
        navigateMode = NavigateMode(obstacleWarner, orientationHelper)

        // Wire mode changes
        modeManager.onModeChanged = { old, new ->
            onModeChanged(old, new)
        }

        // Wire gestures
        gestureHandler.onGesture = { gesture -> handleGesture(gesture) }

        // Wire voice commands
        scope.launch {
            speechRecognizer.transcriptions.collect { text ->
                handleVoiceInput(text)
            }
        }

        // Wire camera frames
        scope.launch {
            cameraManager.frames.collect { frame ->
                processFrame(frame)
            }
        }
    }

    suspend fun startSubsystems() {
        _statusText.value = "Starting voice engine…"
        Log.i(TAG, "startSubsystems() — beginning subsystem initialization")

        // Initialize all subsystems
        Log.i(TAG, "Initializing TTS…")
        val ttsReady = speechSynthesizer.initialize()
        Log.i(TAG, "TTS ready=$ttsReady")

        Log.i(TAG, "Initializing STT…")
        val sttReady = speechRecognizer.initialize()
        Log.i(TAG, "STT ready=$sttReady")

        wakeWordDetector.initialize()

        // Start mic capture so voice commands work
        if (sttReady) {
            speechRecognizer.startListening()
            Log.i(TAG, "STT listening started")
        } else {
            Log.w(TAG, "STT not ready — voice commands will not work")
        }

        if (ttsReady) {
            speechSynthesizer.speak(
                "Atlas Sight is ready. Double-tap or say Hey Atlas to begin.",
                priority = 1,
            )
        } else {
            Log.w(TAG, "TTS not ready — voice output will not work")
        }

        Log.i(TAG, "Loading VLM (this may take 10-30 seconds)…")
        val visionReady = visionModel.load()
        Log.i(TAG, "VLM ready=$visionReady")

        val cameraRunning = cameraManager.isRunning
        Log.i(TAG, "Subsystem summary: tts=$ttsReady stt=$sttReady vlm=$visionReady camera=$cameraRunning")

        _statusText.value = when {
            visionReady && ttsReady -> "Atlas Sight ready. Double-tap or say Hey Atlas."
            !visionReady && ttsReady -> "Voice ready. Vision model loading failed — voice commands and gestures are active."
            !visionReady -> "Vision model failed to load. Voice commands and gestures are active."
            else -> "Voice engine not available. Touch gestures active."
        }

        if (!visionReady && ttsReady) {
            speechSynthesizer.speak(
                "Vision model failed to load. Voice commands and gestures are still active.",
                priority = 2,
            )
        }

        gestureHandler.start()
        orientationHelper.start()
        _isReady.value = true
        Log.i(TAG, "startSubsystems() complete — isReady=true")
    }

    fun shutdown() {
        Log.i(TAG, "Shutting down SightEngine")
        processingJob?.cancel()
        scope.cancel()
        try { cameraManager.stop() } catch (e: Exception) { Log.w(TAG, "Camera stop error", e) }
        try { speechSynthesizer.shutdown() } catch (e: Exception) { Log.w(TAG, "TTS shutdown error", e) }
        try { speechRecognizer.shutdown() } catch (e: Exception) { Log.w(TAG, "STT shutdown error", e) }
        try { wakeWordDetector.shutdown() } catch (e: Exception) { Log.w(TAG, "WakeWord shutdown error", e) }
        try { gestureHandler.stop() } catch (e: Exception) { Log.w(TAG, "Gesture stop error", e) }
        try { orientationHelper.stop() } catch (e: Exception) { Log.w(TAG, "Orientation stop error", e) }
        try { visionModel.release() } catch (e: Exception) { Log.w(TAG, "VLM release error", e) }
    }

    // --- Command routing ---

    fun handleVoiceInput(text: String) {
        Log.d(TAG, "Voice input: '$text'")
        val isWakeWord = wakeWordDetector.checkTranscription(text)
        val command = if (isWakeWord) wakeWordDetector.stripWakeWord(text) else text
        if (command.isBlank()) return

        val match = commandParser.parse(command)
        Log.d(TAG, "Parsed intent=${match.intent} confidence=${match.confidence}")
        if (match.confidence < 0.5f) return

        hapticEngine.vibrate(HapticPattern.ACKNOWLEDGE)
        audioCues.play(AudioCueType.BEEP)
        executeIntent(match)
    }

    fun handleGesture(gesture: GestureHandler.Gesture) {
        Log.d(TAG, "Gesture: $gesture")
        hapticEngine.vibrate(HapticPattern.ACKNOWLEDGE)

        when (gesture) {
            GestureHandler.Gesture.DOUBLE_TAP -> {
                modeManager.switchMode(SightMode.EXPLORE)
                triggerDescribe()
            }
            GestureHandler.Gesture.SWIPE_RIGHT -> {
                modeManager.switchMode(SightMode.READ)
                triggerRead()
            }
            GestureHandler.Gesture.SWIPE_LEFT -> {
                repeatLast()
            }
            GestureHandler.Gesture.SWIPE_UP -> {
                if (modeManager.currentMode.value == SightMode.EXPLORE) {
                    val v = config.cycleVerbosity()
                    speak("Verbosity set to ${v.name.lowercase()}.", 3)
                } else {
                    modeManager.switchMode(SightMode.EXPLORE)
                }
            }
            GestureHandler.Gesture.SWIPE_DOWN -> {
                modeManager.switchMode(SightMode.NAVIGATE)
            }
            GestureHandler.Gesture.LONG_PRESS -> {
                val continuous = config.toggleContinuousMode()
                val state = if (continuous) "on" else "off"
                speak("Continuous mode $state.", 3)
                if (continuous) {
                    hapticEngine.vibrate(HapticPattern.HEARTBEAT)
                } else {
                    hapticEngine.stopHeartbeat()
                }
            }
            GestureHandler.Gesture.TWO_FINGER_TAP -> {
                modeManager.switchMode(SightMode.IDENTIFY)
                triggerIdentify()
            }
            GestureHandler.Gesture.SHAKE -> {
                speak("Emergency mode is not yet available.", 1, SpeedProfile.ALERT)
            }
        }
    }

    private fun executeIntent(match: CommandMatch) {
        when (match.intent) {
            VoiceIntent.DESCRIBE -> {
                modeManager.switchMode(SightMode.EXPLORE)
                triggerDescribe()
            }
            VoiceIntent.READ_TEXT -> {
                modeManager.switchMode(SightMode.READ)
                triggerRead()
            }
            VoiceIntent.LOCATE -> {
                val dir = orientationHelper.getCompassDirection()
                speak("You are facing $dir.", 3)
            }
            VoiceIntent.CHECK_AHEAD -> {
                modeManager.switchMode(SightMode.NAVIGATE)
                triggerNavigationScan()
            }
            VoiceIntent.IDENTIFY -> {
                modeManager.switchMode(SightMode.IDENTIFY)
                triggerIdentify()
            }
            VoiceIntent.NAVIGATE -> {
                modeManager.switchMode(SightMode.NAVIGATE)
            }
            VoiceIntent.FASTER -> {
                config.adjustSpeed(0.25f)
                speak("Speed ${String.format("%.1f", config.speechSpeed.value)}x.", 4)
            }
            VoiceIntent.SLOWER -> {
                config.adjustSpeed(-0.25f)
                speak("Speed ${String.format("%.1f", config.speechSpeed.value)}x.", 4)
            }
            VoiceIntent.NORMAL_SPEED -> {
                config.setSpeed(1.0f)
                speak("Normal speed.", 4)
            }
            VoiceIntent.MAX_SPEED -> {
                config.setSpeed(3.0f)
                speak("Maximum speed.", 4)
            }
            VoiceIntent.LOUDER -> {
                config.adjustVolume(0.2f)
                speak("Volume up.", 4)
            }
            VoiceIntent.SOFTER -> {
                config.adjustVolume(-0.2f)
                speak("Volume down.", 4)
            }
            VoiceIntent.MORE_DETAIL -> {
                val v = config.cycleVerbosity()
                speak("Detail level: ${v.name.lowercase()}.", 3)
            }
            VoiceIntent.LESS_DETAIL -> {
                config.cycleVerbosity() // Will cycle — could also force BRIEF
                speak("Being brief.", 3)
            }
            VoiceIntent.REMEMBER -> {
                val label = match.extras["label"] ?: "location"
                val lm = orientationHelper.addLandmark(label)
                if (lm != null) {
                    speak("Remembered $label.", 3)
                    hapticEngine.vibrate(HapticPattern.SUCCESS)
                } else {
                    speak("Cannot save location. GPS not available.", 3)
                }
            }
            VoiceIntent.REPEAT -> repeatLast()
            VoiceIntent.STOP -> {
                speechSynthesizer.stop()
                hapticEngine.cancel()
                speak("Stopped.", 2)
            }
            VoiceIntent.UNKNOWN -> { /* Ignore unrecognized */ }
        }
    }

    // --- Frame processing ---

    @Volatile
    private var isProcessingFrame = false
    private var lastFrameTime = 0L
    private val frameIntervalMs = 3000L // Process one frame every 3 seconds max

    private fun processFrame(jpegBytes: ByteArray) {
        if (!config.continuousMode.value) return
        if (!visionModel.isReady()) {
            Log.v(TAG, "processFrame skipped — VLM not ready")
            return
        }
        if (isProcessingFrame) return // Skip if previous frame still processing

        val now = System.currentTimeMillis()
        if (now - lastFrameTime < frameIntervalMs) return // Rate limit
        lastFrameTime = now

        val mode = modeManager.currentMode.value
        isProcessingFrame = true
        Log.d(TAG, "Processing frame in $mode mode (${jpegBytes.size} bytes)")
        scope.launch {
            try {
                when (mode) {
                    SightMode.EXPLORE -> processExploreFrame(jpegBytes)
                    SightMode.NAVIGATE -> processNavigateFrame(jpegBytes)
                    SightMode.READ -> { /* Read mode triggered on-demand, not continuous */ }
                    SightMode.IDENTIFY -> { /* Identify triggered on-demand */ }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.e(TAG, "Frame processing error", e)
                speak("Something went wrong. Please try again.", 3)
            } finally {
                isProcessingFrame = false
            }
        }
    }

    private suspend fun processExploreFrame(jpegBytes: ByteArray) {
        Log.d(TAG, "processExploreFrame: ${jpegBytes.size} bytes")
        val scene = visionModel.describeScene(jpegBytes, config.verbosity.value)
        // Always check obstacles first (safety)
        val warnings = exploreMode.processObstacles(scene.objects)
        for (warning in warnings) {
            speak(warning, 1, SpeedProfile.ALERT)
        }
        // Then narrate if novel
        val narration = exploreMode.processScene(scene)
        if (narration != null) {
            speak(narration, 5)
        }
    }

    private suspend fun processNavigateFrame(jpegBytes: ByteArray) {
        Log.d(TAG, "processNavigateFrame: ${jpegBytes.size} bytes")
        val objects = visionModel.detectObjects(jpegBytes)
        val alerts = navigateMode.processObstacles(objects)
        for (alert in alerts) {
            alert.haptic?.let { hapticEngine.vibrate(it) }
            alert.audioCue?.let { audioCues.play(it) }
            speak(alert.text, if (alert.severity == ObstacleSeverity.DANGER) 0 else 2, SpeedProfile.ALERT)
        }
    }

    // --- Triggered actions ---

    private fun triggerDescribe() {
        if (!visionModel.isReady()) {
            Log.w(TAG, "triggerDescribe: VLM not ready")
            speak("Vision is still loading. Please wait.", 2)
            return
        }
        speak("Looking around…", 3)
        scope.launch {
            try {
                val frame = captureCurrentFrame()
                if (frame == null) {
                    Log.w(TAG, "triggerDescribe: no camera frame within timeout")
                    speak("Camera not available.", 2)
                    return@launch
                }
                Log.d(TAG, "triggerDescribe: got frame ${frame.size} bytes, running VLM…")
                val scene = visionModel.describeScene(frame, config.verbosity.value)
                Log.d(TAG, "triggerDescribe: VLM returned ${scene.text.length} chars")
                if (scene.text.isBlank()) {
                    speak("Could not understand the scene. Please try again.", 3)
                } else {
                    speak(scene.text, 4)
                }
            } catch (e: Exception) {
                Log.e(TAG, "triggerDescribe failed", e)
                speak("Unable to describe the scene right now.", 3)
            }
        }
    }

    private fun triggerRead() {
        if (!visionModel.isReady()) {
            Log.w(TAG, "triggerRead: VLM not ready")
            speak("Vision is still loading. Please wait.", 2)
            return
        }
        audioCues.play(AudioCueType.CHIME)
        speak("Reading text…", 3)
        scope.launch {
            try {
                val frame = captureCurrentFrame()
                if (frame == null) {
                    Log.w(TAG, "triggerRead: no camera frame within timeout")
                    speak("Camera not available.", 2)
                    return@launch
                }
                Log.d(TAG, "triggerRead: got frame ${frame.size} bytes, running OCR…")
                val text = visionModel.readText(frame)
                Log.d(TAG, "triggerRead: VLM returned ${text.length} chars")
                val result = readMode.processText(text) ?: readMode.noTextFound()
                speak(result, 4)
            } catch (e: Exception) {
                Log.e(TAG, "triggerRead failed", e)
                speak("Unable to read text right now.", 3)
            }
        }
    }

    private fun triggerIdentify() {
        if (!visionModel.isReady()) {
            Log.w(TAG, "triggerIdentify: VLM not ready")
            speak("Vision is still loading. Please wait.", 2)
            return
        }
        speak("Identifying…", 3)
        scope.launch {
            try {
                val frame = captureCurrentFrame()
                if (frame == null) {
                    Log.w(TAG, "triggerIdentify: no camera frame within timeout")
                    speak("Camera not available.", 2)
                    return@launch
                }
                Log.d(TAG, "triggerIdentify: got frame ${frame.size} bytes")
                val scene = visionModel.describeScene(frame, Verbosity.DETAILED)
                Log.d(TAG, "triggerIdentify: VLM returned ${scene.text.length} chars")
                val result = identifyMode.formatIdentification(scene)
                speak(result, 4)
            } catch (e: Exception) {
                Log.e(TAG, "triggerIdentify failed", e)
                speak("Unable to identify right now.", 3)
            }
        }
    }

    private fun triggerNavigationScan() {
        audioCues.play(AudioCueType.MODE_SWITCH)
        hapticEngine.vibrate(HapticPattern.NAVIGATE)
        val heading = navigateMode.getHeadingAnnouncement()
        speak(heading, 3, SpeedProfile.NAVIGATION)
    }

    private fun repeatLast() {
        val last = contextTracker.getLastText()
        if (last.isNotBlank()) {
            speak(last, 4)
        } else {
            speak("Nothing to repeat.", 4)
        }
    }

    // --- Helpers ---

    private fun speak(text: String, priority: Int, speedProfile: SpeedProfile = SpeedProfile.GENERAL) {
        speechSynthesizer.speak(text, priority, speedProfile)
        _statusText.value = text
    }

    private suspend fun captureCurrentFrame(): ByteArray? {
        if (!cameraManager.isRunning) {
            Log.w(TAG, "captureCurrentFrame: camera is not running")
            return null
        }
        // Wait briefly for next frame from camera
        val frame = withTimeoutOrNull(1000) {
            cameraManager.frames.first()
        }
        if (frame == null) {
            Log.w(TAG, "captureCurrentFrame: timed out waiting for frame")
        }
        return frame
    }

    private fun onModeChanged(old: SightMode, new: SightMode) {
        audioCues.play(AudioCueType.MODE_SWITCH)
        hapticEngine.vibrate(HapticPattern.SUCCESS)
        speak("${new.label} mode.", 2, SpeedProfile.NAVIGATION)
        _statusText.value = "${new.label} mode active"

        // Stop navigation warnings when leaving navigate
        if (old == SightMode.NAVIGATE) {
            navigateMode.reset()
        }
    }
}
