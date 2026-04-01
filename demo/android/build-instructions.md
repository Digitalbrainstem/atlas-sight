# Build Instructions — Atlas Sight for Pixel 9

## Prerequisites

- **Android Studio** Ladybug (2024.2+) with:
  - Android SDK 36
  - NDK 29.0.13113456
  - CMake 3.31+
- **Pixel 9** with USB debugging enabled
- **~2GB free disk** on the phone

## Step 1: Clone llama.cpp

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
```

## Step 2: Download the model

```bash
# Qwen3-0.6B Q4_K_M (~400MB) — fast on Pixel 9
wget -O Qwen3-0.6B-Q4_K_M.gguf \
  "https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf"
```

Alternative (slightly larger, better quality):
```bash
# Qwen2.5-0.5B Instruct Q4_K_M
wget -O qwen2.5-0.5b-instruct-q4_k_m.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
```

## Step 3: Copy Atlas Sight files

```bash
# From the atlas-sight repo
SIGHT_DIR=/path/to/atlas-sight/demo/android

# Copy the custom Activity
cp "$SIGHT_DIR/AtlasSightActivity.kt" \
   examples/llama.android/app/src/main/java/com/example/llama/AtlasSightActivity.kt

# Copy the layout
mkdir -p examples/llama.android/app/src/main/res/layout
cp "$SIGHT_DIR/sight_layout.xml" \
   examples/llama.android/app/src/main/res/layout/sight_layout.xml
```

## Step 4: Update AndroidManifest.xml

Edit `examples/llama.android/app/src/main/AndroidManifest.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <!-- Permissions for Atlas Sight -->
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    <uses-permission android:name="android.permission.VIBRATE" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE"
        android:maxSdkVersion="32" />
    <uses-permission android:name="android.permission.READ_MEDIA_AUDIO" />

    <uses-feature android:name="android.hardware.camera" android:required="true" />

    <application
        android:allowBackup="true"
        android:extractNativeLibs="true"
        android:icon="@mipmap/ic_launcher"
        android:label="Atlas Sight"
        android:supportsRtl="true"
        android:theme="@style/Theme.AppCompat.NoActionBar">

        <!-- Atlas Sight Activity (replaces default MainActivity) -->
        <activity
            android:name=".AtlasSightActivity"
            android:exported="true"
            android:screenOrientation="portrait"
            android:configChanges="orientation|screenSize"
            android:windowSoftInputMode="stateHidden">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

## Step 5: Add CameraX dependencies

Edit `examples/llama.android/app/build.gradle.kts` — add to the `dependencies` block:

```kotlin
dependencies {
    // ... existing dependencies ...

    // CameraX for Atlas Sight
    val cameraxVersion = "1.4.2"
    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")
}
```

## Step 6: Build the APK

1. Open `examples/llama.android` in Android Studio
2. Wait for Gradle sync to complete
3. Select build variant: **release** (or debug for testing)
4. Select target: **Pixel 9** (connected via USB)
5. Click **Run** (▶) or **Build → Build Bundle(s) / APK(s) → Build APK(s)**

The first build takes 5-10 minutes (compiles llama.cpp native code).

**Command line alternative:**
```bash
cd examples/llama.android
./gradlew assembleRelease
# APK at: app/build/outputs/apk/release/app-release.apk
```

## Step 7: Install and set up

```bash
# Install the APK
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Push the model file to Downloads
adb push Qwen3-0.6B-Q4_K_M.gguf /sdcard/Download/

# Or push to app-specific storage
adb push Qwen3-0.6B-Q4_K_M.gguf \
  /sdcard/Android/data/com.example.llama.aichat/files/models/
```

## Step 8: First launch

1. Open **Atlas Sight** from the app drawer
2. Grant **Camera** and **Microphone** permissions when prompted
3. The app will search for a `.gguf` model file in:
   - `/sdcard/Download/` (looks for any .gguf file)
   - `/sdcard/Android/data/com.example.llama.aichat/files/models/`
4. Model loading takes 5-10 seconds on Pixel 9
5. You'll hear "Atlas Sight ready" when the LLM is loaded

## Step 9: Enable offline speech (important!)

For STT/TTS to work without internet:

1. **Settings → System → Languages & Input → Speech**
2. Download **"English (US)"** offline speech recognition pack
3. This ensures `SpeechRecognizer` works in airplane mode

On Pixel 9 this is usually pre-downloaded, but verify it.

## Troubleshooting

### NDK not found
```
Android Studio → Settings → Appearance & Behavior → System Settings
→ Android SDK → SDK Tools → NDK (Side by side) → Install 29.0.13113456
```

### CMake not found
```
Android Studio → Settings → Android SDK → SDK Tools
→ CMake → Install 3.31+
```

### Model not found on launch
The app searches common paths. You can also use `adb` to push directly:
```bash
adb shell mkdir -p /sdcard/Download
adb push your-model.gguf /sdcard/Download/
```

### Build fails with "out of memory"
Add to `gradle.properties`:
```properties
org.gradle.jvmargs=-Xmx4096m
```

### App crashes on launch
Check logcat:
```bash
adb logcat -s AtlasSight:* | head -50
```

## Performance on Pixel 9

| Metric | Value |
|--------|-------|
| Model load time | ~5 seconds |
| First token latency | ~200ms |
| Token generation | ~15-25 tok/s |
| RAM usage | ~800MB |
| Battery impact | Moderate (CPU inference) |

The Tensor G4 in Pixel 9 handles 0.6B Q4 models very well.
