package dev.atlascortex.sight.platform

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.view.accessibility.AccessibilityManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * Voice-guided permission flow — speaks to the user during requests.
 * No visual dependency for permission explanations.
 */
class Permissions(private val context: Context) {

    companion object {
        const val REQUEST_CODE = 1001
        val REQUIRED_PERMISSIONS = arrayOf(
            Manifest.permission.CAMERA,
            Manifest.permission.RECORD_AUDIO,
        )
        val OPTIONAL_PERMISSIONS = arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
        )
    }

    fun hasCameraPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED

    fun hasMicrophonePermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    fun hasAllRequired(): Boolean =
        REQUIRED_PERMISSIONS.all {
            ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
        }

    fun getMissingPermissions(): List<String> =
        REQUIRED_PERMISSIONS.filter {
            ContextCompat.checkSelfPermission(context, it) != PackageManager.PERMISSION_GRANTED
        }

    fun requestPermissions(activity: Activity) {
        val missing = getMissingPermissions()
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(
                activity,
                missing.toTypedArray(),
                REQUEST_CODE,
            )
        }
    }

    /** Get voice guidance text for a specific permission. */
    fun getPermissionGuidance(permission: String): String = when (permission) {
        Manifest.permission.CAMERA ->
            "Atlas Sight needs camera access to see the world for you. " +
            "Please allow camera permission when prompted."
        Manifest.permission.RECORD_AUDIO ->
            "Atlas Sight needs microphone access for voice commands. " +
            "Please allow microphone permission when prompted."
        Manifest.permission.ACCESS_FINE_LOCATION ->
            "Location access helps with navigation and landmark features. " +
            "This is optional."
        else -> "Please allow this permission for full functionality."
    }

    /** Check if TalkBack is active. */
    fun isTalkBackEnabled(): Boolean {
        val am = context.getSystemService(Context.ACCESSIBILITY_SERVICE) as? AccessibilityManager
        return am?.isTouchExplorationEnabled == true
    }
}
