package dev.atlascortex.sight.platform

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.view.GestureDetector
import android.view.MotionEvent
import dev.atlascortex.sight.core.SightMode
import kotlin.math.abs
import kotlin.math.sqrt

/**
 * 8-gesture handler: double-tap, swipe L/R/U/D, long-press, 2-finger-tap, shake.
 */
class GestureHandler(context: Context) : SensorEventListener {

    enum class Gesture {
        DOUBLE_TAP,      // Describe scene
        SWIPE_RIGHT,     // Read text mode
        SWIPE_LEFT,      // Repeat last spoken
        SWIPE_UP,        // More detail / Explore mode
        SWIPE_DOWN,      // Navigate mode
        LONG_PRESS,      // Toggle continuous mode
        TWO_FINGER_TAP,  // Identify object
        SHAKE,           // Reserved for emergency
    }

    var onGesture: ((Gesture) -> Unit)? = null

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private var lastShakeTime = 0L
    private val shakeThreshold = 18f // m/s^2

    private var twoFingerDown = false
    private var twoFingerStartTime = 0L

    val gestureDetector = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDoubleTap(e: MotionEvent): Boolean {
            onGesture?.invoke(Gesture.DOUBLE_TAP)
            return true
        }

        override fun onLongPress(e: MotionEvent) {
            onGesture?.invoke(Gesture.LONG_PRESS)
        }

        override fun onFling(
            e1: MotionEvent?,
            e2: MotionEvent,
            velocityX: Float,
            velocityY: Float,
        ): Boolean {
            val e1x = e1?.x ?: return false
            val e1y = e1.y
            val dx = e2.x - e1x
            val dy = e2.y - e1y

            if (abs(dx) > abs(dy) && abs(dx) >= 80) {
                // Horizontal swipe
                if (dx > 0) onGesture?.invoke(Gesture.SWIPE_RIGHT)
                else onGesture?.invoke(Gesture.SWIPE_LEFT)
                return true
            } else if (abs(dy) > abs(dx) && abs(dy) >= 80) {
                // Vertical swipe
                if (dy < 0) onGesture?.invoke(Gesture.SWIPE_UP)
                else onGesture?.invoke(Gesture.SWIPE_DOWN)
                return true
            }
            return false
        }
    })

    fun start() {
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        }
    }

    fun stop() {
        sensorManager.unregisterListener(this)
    }

    /** Call from Activity.dispatchTouchEvent() to handle two-finger taps. */
    fun onTouchEvent(event: MotionEvent): Boolean {
        gestureDetector.onTouchEvent(event)

        // Two-finger tap detection
        when (event.actionMasked) {
            MotionEvent.ACTION_POINTER_DOWN -> {
                if (event.pointerCount == 2) {
                    twoFingerDown = true
                    twoFingerStartTime = System.currentTimeMillis()
                }
            }
            MotionEvent.ACTION_POINTER_UP, MotionEvent.ACTION_UP -> {
                if (twoFingerDown && event.pointerCount <= 2) {
                    val elapsed = System.currentTimeMillis() - twoFingerStartTime
                    if (elapsed <= 400) {
                        onGesture?.invoke(Gesture.TWO_FINGER_TAP)
                    }
                    twoFingerDown = false
                }
            }
        }
        return true
    }

    // --- Shake detection via accelerometer ---
    override fun onSensorChanged(event: SensorEvent) {
        if (event.sensor.type != Sensor.TYPE_ACCELEROMETER) return
        val x = event.values[0]
        val y = event.values[1]
        val z = event.values[2]
        val acceleration = sqrt(x * x + y * y + z * z)

        if (acceleration > shakeThreshold) {
            val now = System.currentTimeMillis()
            if (now - lastShakeTime > 1000) { // Debounce 1s
                lastShakeTime = now
                onGesture?.invoke(Gesture.SHAKE)
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}
