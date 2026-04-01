# ONNX Runtime
-keep class ai.onnxruntime.** { *; }
-dontwarn ai.onnxruntime.**

# Sherpa-ONNX
-keep class com.k2fsa.sherpa.onnx.** { *; }
-dontwarn com.k2fsa.sherpa.onnx.**

# Keep data classes for reflection
-keep class dev.atlascortex.sight.core.** { *; }

# Compose
-dontwarn androidx.compose.**
