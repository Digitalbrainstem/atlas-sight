# Atlas Sight — Android App

A sideloadable Android app that runs a vision assistant **100% on-device**.
Built on top of the official [llama.cpp Android example](https://github.com/ggml-org/llama.cpp/tree/master/examples/llama.android).

No cloud. No internet. No subscription. Just a phone helping someone see.

## What you get

A native Android app with:
- **Full-screen camera** (rear, via CameraX)
- **On-device LLM** (Qwen3.5-0.8B Q4 via llama.cpp JNI — ~500MB)
- **Offline STT** (Android SpeechRecognizer — built into Pixel 9)
- **Offline TTS** (Android TextToSpeech — built into Pixel 9)
- **Accessibility gestures** (double-tap, long-press, swipe, shake)
- **Haptic feedback** (vibration on every action)

Total APK: ~15MB + 500MB model file = ~515MB on device.

## Quick Start

See [build-instructions.md](build-instructions.md) for the full step-by-step guide.

**TL;DR:**

```bash
# 1. Clone llama.cpp
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp/examples/llama.android

# 2. Copy Atlas Sight files over the default app
cp /path/to/atlas-sight/demo/android/AtlasSightActivity.kt \
   app/src/main/java/com/example/llama/AtlasSightActivity.kt
cp /path/to/atlas-sight/demo/android/sight_layout.xml \
   app/src/main/res/layout/sight_layout.xml

# 3. Update AndroidManifest.xml (see build-instructions.md)

# 4. Open in Android Studio → Build → Run on Pixel 9

# 5. Push model to phone
adb push Qwen3-0.6B-Q4_K_M.gguf /sdcard/Download/
```

## Architecture

```
┌──────────────── Atlas Sight APK ─────────────────┐
│                                                   │
│  AtlasSightActivity.kt                           │
│  ├── CameraX Preview (rear camera)               │
│  ├── GestureDetector (double-tap, swipe, etc.)   │
│  ├── SpeechRecognizer (offline STT)              │
│  ├── TextToSpeech (offline TTS)                  │
│  ├── SensorManager (shake detection)             │
│  └── Vibrator (haptic feedback)                  │
│           │                                       │
│           ▼                                       │
│  InferenceEngine (from :lib module)              │
│  └── libai-chat.so (llama.cpp JNI)               │
│      └── Qwen3.5-0.8B Q4_K_M.gguf               │
│                                                   │
│  RAM: ~800MB  •  100% offline  •  arm64-v8a      │
└───────────────────────────────────────────────────┘
```

## Gestures

| Gesture | Action |
|---------|--------|
| Double-tap | Capture frame → describe via LLM → speak |
| Long press | Start voice input → ask LLM → speak answer |
| Swipe right | Switch to "read text" mode |
| Swipe left | Repeat last description |
| Swipe up | Increase speech rate |
| Swipe down | Decrease speech rate |
| Shake | Emergency "where am I?" mode |

## Files

| File | Description |
|------|-------------|
| `AtlasSightActivity.kt` | Main activity — replaces the default chat UI |
| `sight_layout.xml` | Layout — full-screen camera + overlay |
| `build-instructions.md` | Step-by-step build guide for Pixel 9 |
| `README.md` | This file |
