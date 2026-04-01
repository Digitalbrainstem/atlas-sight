package dev.atlascortex.sight

import android.os.Bundle
import android.view.MotionEvent
import android.view.accessibility.AccessibilityEvent
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.*
import androidx.lifecycle.lifecycleScope
import dev.atlascortex.sight.core.SightEngine
import dev.atlascortex.sight.core.SightMode
import dev.atlascortex.sight.platform.Permissions
import dev.atlascortex.sight.ui.SightScreen
import dev.atlascortex.sight.ui.theme.AtlasSightTheme
import dev.atlascortex.sight.util.ModelDownloader
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Single activity — voice-first, no visual dependency.
 * TalkBack + announceForAccessibility() for all state changes.
 */
class MainActivity : ComponentActivity() {

    private lateinit var engine: SightEngine
    private lateinit var modelDownloader: ModelDownloader
    private lateinit var permissions: Permissions

    // Compose state
    private val statusText = mutableStateOf("Initializing Atlas Sight…")
    private val currentMode = mutableStateOf(SightMode.EXPLORE)
    private val isReady = mutableStateOf(false)
    private val isDownloading = mutableStateOf(false)
    private val downloadProgress = mutableFloatStateOf(0f)

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { results ->
        val allGranted = results.values.all { it }
        if (allGranted) {
            announce("Permissions granted. Starting Atlas Sight.")
            startEngine()
        } else {
            announce("Some permissions were denied. Atlas Sight needs camera and microphone access.")
            statusText.value = "Permissions needed. Please restart and allow access."
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        engine = SightEngine(this)
        modelDownloader = ModelDownloader(this)
        permissions = Permissions(this)

        engine.initialize()

        // Observe engine state
        lifecycleScope.launch {
            engine.statusText.collectLatest { text ->
                statusText.value = text
                announce(text)
            }
        }
        lifecycleScope.launch {
            engine.isReady.collectLatest { ready ->
                isReady.value = ready
            }
        }
        lifecycleScope.launch {
            engine.modeManager.currentMode.collectLatest { mode ->
                currentMode.value = mode
            }
        }

        setContent {
            AtlasSightTheme {
                SightScreen(
                    statusText = statusText.value,
                    currentMode = currentMode.value,
                    isReady = isReady.value,
                    isDownloading = isDownloading.value,
                    downloadProgress = downloadProgress.floatValue,
                    onActivate = { onActivateButton() },
                )
            }
        }

        // Start permission flow
        checkPermissionsAndStart()
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        if (::engine.isInitialized) {
            engine.gestureHandler.onTouchEvent(ev)
        }
        return super.dispatchTouchEvent(ev)
    }

    override fun onResume() {
        super.onResume()
        if (::engine.isInitialized && isReady.value) {
            engine.gestureHandler.start()
            engine.orientationHelper.start()
            engine.cameraManager.start(this)
        }
    }

    override fun onPause() {
        super.onPause()
        if (::engine.isInitialized) {
            engine.gestureHandler.stop()
            engine.orientationHelper.stop()
            engine.cameraManager.stop()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (::engine.isInitialized) {
            engine.shutdown()
        }
    }

    private fun checkPermissionsAndStart() {
        if (permissions.hasAllRequired()) {
            startEngine()
        } else {
            // Voice-guided permission request
            val missing = permissions.getMissingPermissions()
            for (perm in missing) {
                announce(permissions.getPermissionGuidance(perm))
            }
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun startEngine() {
        lifecycleScope.launch {
            // Check models first
            if (!modelDownloader.allModelsReady()) {
                isDownloading.value = true
                // Observe download progress
                launch {
                    modelDownloader.progress.collectLatest { progress ->
                        downloadProgress.floatValue = progress.progress
                    }
                }
                val success = modelDownloader.downloadMissingModels { announcement ->
                    announce(announcement)
                    statusText.value = announcement
                }
                isDownloading.value = false
                if (!success) {
                    statusText.value = "Model download failed. Please check internet and restart."
                    return@launch
                }
            }

            // Start all subsystems
            engine.cameraManager.start(this@MainActivity)
            engine.startSubsystems()
        }
    }

    private fun onActivateButton() {
        if (isReady.value) {
            engine.handleGesture(
                dev.atlascortex.sight.platform.GestureHandler.Gesture.DOUBLE_TAP
            )
        }
    }

    /** Announce to TalkBack and other accessibility services. */
    private fun announce(text: String) {
        try {
            window?.decorView?.announceForAccessibility(text)
        } catch (_: Exception) {
            // Accessibility announce is best-effort
        }
    }
}
