package dev.atlascortex.sight.platform

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Rect
import android.graphics.YuvImage
import android.util.Log
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import java.io.ByteArrayOutputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * CameraX lifecycle-aware camera for continuous frame capture.
 * Provides JPEG byte arrays at 640x480 resolution.
 */
class CameraManager(private val context: Context) {

    companion object {
        private const val TAG = "CameraManager"
        const val TARGET_WIDTH = 640
        const val TARGET_HEIGHT = 480
    }

    private var cameraProvider: ProcessCameraProvider? = null
    private var imageAnalysis: ImageAnalysis? = null
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()

    private val _frames = MutableSharedFlow<ByteArray>(
        replay = 0,
        extraBufferCapacity = 1,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )
    val frames: SharedFlow<ByteArray> = _frames.asSharedFlow()

    var isRunning: Boolean = false
        private set

    @Volatile
    private var frameCount = 0L

    fun start(lifecycleOwner: LifecycleOwner) {
        if (isRunning) {
            Log.d(TAG, "start() called but already running")
            return
        }
        Log.i(TAG, "Starting camera…")
        val providerFuture = ProcessCameraProvider.getInstance(context)
        providerFuture.addListener({
            try {
                val provider = providerFuture.get()
                cameraProvider = provider
                bindCamera(provider, lifecycleOwner)
            } catch (e: Exception) {
                Log.e(TAG, "Camera provider init failed", e)
            }
        }, ContextCompat.getMainExecutor(context))
    }

    fun stop() {
        Log.i(TAG, "Stopping camera (frames emitted: $frameCount)")
        isRunning = false
        try { cameraProvider?.unbindAll() } catch (_: Exception) { }
    }

    /** Capture a single frame as JPEG bytes. */
    fun captureFrame(): ByteArray? {
        // Latest frame is delivered via SharedFlow from the analyzer
        return null // Direct capture not supported — use frames flow
    }

    private fun bindCamera(provider: ProcessCameraProvider, lifecycleOwner: LifecycleOwner) {
        provider.unbindAll()

        val cameraSelector = CameraSelector.Builder()
            .requireLensFacing(CameraSelector.LENS_FACING_BACK)
            .build()

        imageAnalysis = ImageAnalysis.Builder()
            .setTargetResolution(android.util.Size(TARGET_WIDTH, TARGET_HEIGHT))
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
            .build()
            .also { analysis ->
                analysis.setAnalyzer(executor) { imageProxy ->
                    processFrame(imageProxy)
                }
            }

        try {
            provider.bindToLifecycle(
                lifecycleOwner,
                cameraSelector,
                imageAnalysis,
            )
            isRunning = true
            Log.i(TAG, "Camera bound successfully — frames will flow via SharedFlow")
        } catch (e: Exception) {
            Log.e(TAG, "Camera bind failed", e)
            isRunning = false
        }
    }

    private fun processFrame(imageProxy: ImageProxy) {
        try {
            val jpeg = imageProxyToJpeg(imageProxy)
            if (jpeg != null) {
                val emitted = _frames.tryEmit(jpeg)
                frameCount++
                if (frameCount == 1L) {
                    Log.i(TAG, "First camera frame emitted (${jpeg.size} bytes, ${imageProxy.width}x${imageProxy.height})")
                }
                if (frameCount % 300 == 0L) {
                    Log.d(TAG, "Camera frames emitted: $frameCount (latest ${jpeg.size} bytes, emitted=$emitted)")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Frame processing error", e)
        } finally {
            imageProxy.close()
        }
    }

    private fun imageProxyToJpeg(imageProxy: ImageProxy): ByteArray? {
        return try {
            val yBuffer = imageProxy.planes[0].buffer
            val uBuffer = imageProxy.planes[1].buffer
            val vBuffer = imageProxy.planes[2].buffer
            val ySize = yBuffer.remaining()
            val uSize = uBuffer.remaining()
            val vSize = vBuffer.remaining()
            val nv21 = ByteArray(ySize + uSize + vSize)
            yBuffer.get(nv21, 0, ySize)
            vBuffer.get(nv21, ySize, vSize)
            uBuffer.get(nv21, ySize + vSize, uSize)

            val yuvImage = YuvImage(nv21, ImageFormat.NV21,
                imageProxy.width, imageProxy.height, null)
            val out = ByteArrayOutputStream()
            yuvImage.compressToJpeg(
                Rect(0, 0, imageProxy.width, imageProxy.height),
                80, out
            )
            out.toByteArray()
        } catch (_: Exception) {
            null
        }
    }
}
