package dev.atlascortex.sight.core

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import kotlin.math.*

/**
 * 8-point compass, landmark bookmarks, and Haversine distance.
 */
class OrientationHelper(context: Context) : SensorEventListener, LocationListener {

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager

    private val gravity = FloatArray(3)
    private val geomagnetic = FloatArray(3)
    private val rotationMatrix = FloatArray(9)
    private val orientation = FloatArray(3)

    private var currentAzimuth: Float = 0f
    private var currentLocation: Location? = null
    private val landmarks = mutableListOf<Landmark>()

    fun start() {
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        }
        sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        }
        try {
            locationManager?.requestLocationUpdates(
                LocationManager.FUSED_PROVIDER, 5000L, 5f, this
            )
        } catch (_: SecurityException) {
            // Location permission not granted — orientation still works
        }
    }

    fun stop() {
        sensorManager.unregisterListener(this)
        try {
            locationManager?.removeUpdates(this)
        } catch (_: SecurityException) { }
    }

    /** 8-point compass direction name. */
    fun getCompassDirection(): String {
        val bearing = ((currentAzimuth + 360) % 360)
        return when {
            bearing < 22.5f || bearing >= 337.5f -> "north"
            bearing < 67.5f -> "northeast"
            bearing < 112.5f -> "east"
            bearing < 157.5f -> "southeast"
            bearing < 202.5f -> "south"
            bearing < 247.5f -> "southwest"
            bearing < 292.5f -> "west"
            else -> "northwest"
        }
    }

    fun getAzimuthDegrees(): Float = currentAzimuth

    fun addLandmark(name: String): Landmark? {
        val loc = currentLocation ?: return null
        val lm = Landmark(name, loc.latitude, loc.longitude)
        landmarks.add(lm)
        return lm
    }

    fun getLandmarks(): List<Landmark> = landmarks.toList()

    /** Haversine distance in meters to a landmark. */
    fun distanceTo(landmark: Landmark): Float? {
        val loc = currentLocation ?: return null
        return haversine(loc.latitude, loc.longitude, landmark.latitude, landmark.longitude)
    }

    /** Bearing to landmark as a compass direction. */
    fun directionTo(landmark: Landmark): String? {
        val loc = currentLocation ?: return null
        val bearing = bearingTo(loc.latitude, loc.longitude, landmark.latitude, landmark.longitude)
        val relative = ((bearing - currentAzimuth + 360) % 360)
        return when {
            relative < 22.5f || relative >= 337.5f -> "straight ahead"
            relative < 67.5f -> "ahead to your right"
            relative < 112.5f -> "to your right"
            relative < 157.5f -> "behind to your right"
            relative < 202.5f -> "behind you"
            relative < 247.5f -> "behind to your left"
            relative < 292.5f -> "to your left"
            else -> "ahead to your left"
        }
    }

    // --- SensorEventListener ---
    override fun onSensorChanged(event: SensorEvent) {
        when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
                System.arraycopy(event.values, 0, gravity, 0, 3)
            }
            Sensor.TYPE_MAGNETIC_FIELD -> {
                System.arraycopy(event.values, 0, geomagnetic, 0, 3)
            }
        }
        if (SensorManager.getRotationMatrix(rotationMatrix, null, gravity, geomagnetic)) {
            SensorManager.getOrientation(rotationMatrix, orientation)
            currentAzimuth = Math.toDegrees(orientation[0].toDouble()).toFloat()
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    // --- LocationListener ---
    override fun onLocationChanged(location: Location) {
        currentLocation = location
    }

    @Deprecated("Required for API compat")
    override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
    override fun onProviderEnabled(provider: String) {}
    override fun onProviderDisabled(provider: String) {}

    // --- Haversine math ---
    private fun haversine(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Float {
        val R = 6371000.0 // Earth radius in meters
        val dLat = Math.toRadians(lat2 - lat1)
        val dLon = Math.toRadians(lon2 - lon1)
        val a = sin(dLat / 2).pow(2) +
                cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) *
                sin(dLon / 2).pow(2)
        val c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return (R * c).toFloat()
    }

    private fun bearingTo(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Float {
        val dLon = Math.toRadians(lon2 - lon1)
        val rLat1 = Math.toRadians(lat1)
        val rLat2 = Math.toRadians(lat2)
        val y = sin(dLon) * cos(rLat2)
        val x = cos(rLat1) * sin(rLat2) - sin(rLat1) * cos(rLat2) * cos(dLon)
        return ((Math.toDegrees(atan2(y, x)) + 360) % 360).toFloat()
    }
}
