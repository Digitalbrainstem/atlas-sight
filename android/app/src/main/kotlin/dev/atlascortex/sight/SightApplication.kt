package dev.atlascortex.sight

import android.app.Application
import android.util.Log

/**
 * Application-level initialization.
 * Pre-checks model availability before Activity starts.
 */
class SightApplication : Application() {
    companion object {
        const val TAG = "AtlasSight"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "Atlas Sight application starting")
    }
}
