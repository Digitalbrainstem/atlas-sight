# Atlas Sight — Native App Plan (Android + iOS)

> A voice-first accessibility app for visually impaired users.
> Fully offline. No cloud. No configuration. Works out of the box.

## Architecture: Local-First, Zero-Server, Cross-Platform

Everything runs on-device. No Atlas Cortex server required. No internet after
initial model download. This is critical — visually impaired users need this to
work at the grocery store, on the sidewalk, anywhere.

**Cross-platform strategy:** Shared core logic (modes, commands, data models,
audio synthesis) with platform-native UI and hardware access. Sherpa-ONNX and
ONNX Runtime provide the same models on both Android and iOS.

## Target

- **v1:** Android (Personal use + sideload testing)
- **v2:** iOS port (same architecture, Swift + SwiftUI)
- **v3:** Play Store + App Store distribution
- Android package: `dev.atlascortex.sight`
- iOS bundle: `dev.atlascortex.sight`

---

## Tech Stack

| Component | Technology | Size | Why |
|-----------|-----------|------|-----|
| **Language** | Kotlin (Android) / Swift (iOS) | — | Native per-platform, best accessibility API access |
| **UI Framework** | Jetpack Compose (Android) / SwiftUI (iOS) | — | Minimal visual UI, needed for TalkBack/VoiceOver |
| **Camera** | CameraX (Android) / AVFoundation (iOS) | — | Modern, lifecycle-aware, preview + capture |
| **VLM (Vision)** | Qwen3-VL-2B via ONNX Runtime | ~800MB | Smallest Qwen VL, 32-lang OCR, 256K ctx, Apache 2.0 |
| **STT** | Sherpa-ONNX + Whisper small | ~200MB | Cross-platform (Android+iOS), fully offline, Kotlin+Swift API |
| **TTS** | Sherpa-ONNX + Piper voices | ~15MB | Cross-platform (Android+iOS), configurable speed, priority queue |
| **Gestures** | GestureDetector / UIGestureRecognizer | — | Touch + accelerometer (shake) |
| **Haptics** | VibrationEffect / UIImpactFeedbackGenerator | — | Predefined patterns per platform |
| **Audio Cues** | AudioTrack / AVAudioEngine (PCM synthesis) | — | Sine wave tones, zero audio files shipped |
| **Total on-device** | | **~1.0GB** | Fits comfortably on any modern phone |

### Why Qwen3-VL-2B?

- **Apache 2.0** — fully open, no vendor can revoke your license
- **2B params** — smallest in the Qwen3-VL family, ~800MB Q4 GGUF
- **32-language OCR** — critical for reading signs, menus, labels worldwide
- **256K context** — handles complex multi-turn conversations about scenes
- Stays in the **Qwen family** (consistent with Atlas Cortex's Qwen3.5 stack)
- ONNX Runtime available on both Android and iOS

### Why Sherpa-ONNX for STT + TTS?

- **Cross-platform** — same models, same API on Android (Kotlin) and iOS (Swift)
- **Truly offline** — no Google Play Services, no Apple cloud, no hidden network calls
- **Consistent experience** — identical voice quality on both platforms
- Ships Whisper models (75MB-1.5GB, pick your quality/size tradeoff)
- Piper TTS voices (~15MB each) with configurable speed
- Wake word detection built-in
- Open source (Apache 2.0)

---

## App Structure

### Shared Core (Kotlin Multiplatform or mirrored logic)

```
core/
├── SightEngine               # Main orchestrator (binds all subsystems)
├── ModeManager               # 4-mode state machine + dispatcher
├── Config                    # User preferences (speed, volume, verbosity)
├── CommandParser              # 25+ voice intents, pattern matching
├── ObstacleWarner             # Severity classification + directional warnings
├── OrientationHelper          # Compass + landmark bookmarks
├── ContextTracker             # Deduplication (Jaccard similarity)
├── SessionHistory             # Rolling scene window, bookmarks
├── AudioCueSynthesizer        # Sine wave tone generation (PCM)
├── Models                     # Data classes: Scene, DetectedObject, Obstacle, etc.
└── modes/
    ├── ExploreMode            # Continuous scene narration
    ├── ReadMode               # Text reading (signs, menus, labels)
    ├── NavigateMode           # Obstacle scanning + compass
    └── IdentifyMode           # Point-and-ask object identification
```

### Android (`android/`)

```
dev.atlascortex.sight/
├── app/
│   ├── SightApplication.kt          # App init, model preloading
│   ├── MainActivity.kt              # Single activity, voice-first
│   └── ui/
│       ├── SightScreen.kt           # Minimal Compose UI (status + large buttons)
│       └── theme/Theme.kt           # High contrast, large text
├── platform/
│   ├── CameraManager.kt             # CameraX lifecycle, frame capture
│   ├── VisionModel.kt               # Qwen3-VL-2B via ONNX Runtime
│   ├── SpeechRecognizer.kt          # Sherpa-ONNX Whisper STT
│   ├── SpeechSynthesizer.kt         # Sherpa-ONNX Piper TTS + priority queue
│   ├── WakeWordDetector.kt          # "Hey Atlas" detection
│   ├── GestureHandler.kt            # GestureDetector + SensorManager
│   ├── HapticEngine.kt              # VibrationEffect patterns
│   └── Permissions.kt               # Camera + mic permission flow (voice-guided)
└── util/
    └── ModelDownloader.kt            # First-run model download with voice progress
```

### iOS (`ios/`) — v2

```
AtlasSight/
├── App/
│   ├── AtlasSightApp.swift           # App entry, model preloading
│   ├── ContentView.swift             # Minimal SwiftUI (status + large buttons)
│   └── Theme.swift                   # High contrast, large text
├── Platform/
│   ├── CameraManager.swift           # AVFoundation frame capture
│   ├── VisionModel.swift             # Qwen3-VL-2B via ONNX Runtime
│   ├── SpeechRecognizer.swift        # Sherpa-ONNX Whisper STT
│   ├── SpeechSynthesizer.swift       # Sherpa-ONNX Piper TTS + priority queue
│   ├── WakeWordDetector.swift        # "Hey Atlas" detection
│   ├── GestureHandler.swift          # UIGestureRecognizer + CoreMotion
│   ├── HapticEngine.swift            # UIImpactFeedbackGenerator patterns
│   └── Permissions.swift             # Camera + mic permission flow (voice-guided)
└── Util/
    └── ModelDownloader.swift          # First-run model download with voice progress
```

---

## 4 Interaction Modes (v1)

| Mode | Trigger | What it does |
|------|---------|-------------|
| **Explore** | Default / swipe up / "describe" | Continuous scene narration every 0.5s, obstacle alerts, 3 verbosity levels |
| **Read** | Swipe right / "read the text" | OCR via VLM, natural reading order (top-to-bottom, left-to-right) |
| **Navigate** | Swipe down / "start navigation" | Continuous obstacle scanning, escalating audio+haptic warnings, compass |
| **Identify** | 2-finger tap / "what is this?" | Point-and-ask single object, follow-up Q&A |

**Future (if users request):** Emergency mode (shake to max context dump for 911)

---

## Gesture Map

| Gesture | Action | Detection |
|---------|--------|-----------|
| Double-tap | Describe scene | 2 taps within 350ms, <40px drift |
| Swipe right | Read text mode | >=80px horizontal drag |
| Swipe left | Repeat last spoken | >=80px horizontal drag |
| Swipe up | More detail / Explore mode | >=80px vertical drag |
| Swipe down | Navigate mode | >=80px vertical drag |
| Long press | Toggle continuous mode | Hold 0.8s |
| 2-finger tap | Identify object | 2 pointers, <=400ms |
| Shake | (Reserved for future Emergency) | Accelerometer peaks >=18 m/s^2 |

---

## Voice Commands (25+ intents)

**Wake word:** "Hey Atlas" or "Atlas"

| Category | Commands | Intent |
|----------|----------|--------|
| **Scene** | "What do you see?" "Describe" | DESCRIBE |
| **Text** | "Read the sign" "What does it say?" | READ_TEXT |
| **Location** | "Where am I?" | LOCATE |
| **Safety** | "Check ahead" "Any obstacles?" | CHECK_AHEAD |
| **Identify** | "What is this?" "Tell me about this" | IDENTIFY |
| **Navigate** | "Start navigation" "Guide me" | NAVIGATE |
| **Speed** | "Faster" "Slower" "Normal speed" | FASTER/SLOWER |
| **Volume** | "Louder" "Quieter" | LOUDER/SOFTER |
| **Detail** | "More detail" "Be brief" | MORE_DETAIL/LESS_DETAIL |
| **Memory** | "Remember this as [label]" | REMEMBER |
| **Control** | "Repeat" "Stop" | REPEAT/STOP |

---

## Haptic Patterns

| Pattern | Timing | Meaning |
|---------|--------|---------|
| Single pulse | 100ms | Command acknowledged |
| Double pulse | 60ms + 80ms gap + 60ms | Success/ready |
| Triple pulse | 120ms x 3 | Warning |
| Rapid 5x | 50ms x 5, 30ms gaps | **Danger — stop moving** |
| Heartbeat | 100ms on, 600ms off (loop) | Continuous mode active |
| Navigate | 70ms x 3, 100ms gaps | Navigation active |

---

## Audio Cues (Synthesized, no audio files)

| Sound | Frequency | Meaning |
|-------|-----------|---------|
| Beep | 800 Hz, 100ms | Command acknowledged |
| Chime | 1000 to 1250 Hz sweep | Text detected / ready |
| Warning | 1200 to 1800 Hz, 400ms | Obstacle approaching |
| Danger | Pulsing 1600 Hz x 5 | **Immediate danger** |
| Rising tone | 600 to 1400 Hz | Getting closer |
| Falling tone | 1400 to 600 Hz | Receding |
| Mode switch | Two-tone sweep | Mode changed |

All tones: 22,050 Hz sample rate, 16-bit PCM, 2ms fade-in/out.

---

## Build Phases

### Phase 1: Foundation
- Project scaffolding (Kotlin, Gradle, dependencies)
- Minimal UI (status text + large button, high contrast)
- Permission flow (camera + mic, voice-guided)
- Model download on first launch (voice progress announcements)
- TalkBack accessibility integration

### Phase 2: Voice Engine
- Sherpa-ONNX integration (STT + TTS)
- Wake word detection ("Hey Atlas")
- Command parser (25+ intents)
- Priority speech queue with speed profiles
- Haptic engine + audio cue synthesizer

### Phase 3: Vision Engine
- CameraX integration (continuous frame capture)
- Gemma 3n via MediaPipe/LiteRT inference
- Scene description prompting
- Object detection with distance estimation
- OCR / text reading

### Phase 4: Modes + Navigation
- Mode state machine (Explore, Read, Navigate, Identify)
- Gesture handler (8 gestures)
- Explore mode (continuous narration + deduplication)
- Read mode (OCR + natural reading order)
- Navigate mode (obstacle scanning + compass)
- Identify mode (point-and-ask)

### Phase 5: iOS Port
- Xcode project scaffolding (SwiftUI, same bundle ID)
- Sherpa-ONNX Swift integration (STT + TTS — same models as Android)
- Qwen3-VL-2B via ONNX Runtime for iOS
- AVFoundation camera, CoreMotion gestures, UIImpactFeedbackGenerator haptics
- Port all shared core logic (modes, commands, audio synthesis)
- VoiceOver accessibility audit

### Phase 6: Polish + Distribution
- Context tracker (dedup repeated descriptions)
- Session history + bookmarks
- User preferences persistence
- Orientation/compass integration
- Play Store + App Store preparation (signing, listings, screenshots)
- Accessibility audit (TalkBack + VoiceOver end-to-end testing)

---

## Key Design Principles

1. **Zero visual UI dependency** — every interaction is voice + haptic + audio cue
2. **Works offline** — all models on-device, no network after first download
3. **No configuration** — works out of the box, model auto-downloads
4. **Error-friendly** — exceptions become spoken messages, never stack traces
5. **Safety-first** — obstacle warnings always at normal speed, never skipped
6. **Memory-efficient** — single VLM handles scene + OCR + detection
7. **Dedup** — Jaccard similarity prevents boring repetition
8. **Graceful degradation** — works without camera (voice-only), without mic (touch-only)

---

## Hardware Requirements

### Android
- Android 13+ (API 33)
- 4GB+ RAM (800MB VLM + 200MB STT + 15MB TTS + OS overhead)
- Camera (rear preferred, front fallback)
- Microphone
- ~1.5GB storage for models
- GPS + compass (optional, enhances navigation)

### iOS (v2)
- iOS 16+
- iPhone 12 or newer (A14+ for ONNX Runtime performance)
- Camera, microphone
- ~1.5GB storage for models
- Same GPS/compass optional enhancements

---

## Model Download Strategy

On first launch:
1. Speak: "Welcome to Atlas Sight. Downloading AI models. This only happens once."
2. Download Qwen3-VL-2B Q4 GGUF (~800MB) with voice progress every 25%
3. Download Sherpa-ONNX Whisper small model (~200MB)
4. Download Piper TTS voice (~15MB)
5. Speak: "Atlas Sight is ready. Double-tap or say Hey Atlas to begin."

Models stored in app-private storage. Re-download button in settings if corrupted.
Total first-download: ~1.0GB (one-time, cached forever).

---

## Eye Logo

The Atlas Sight icon is a stylized eye using Atlas brand colors:
- **Background:** Dark slate (#0F172A)
- **Eye:** White almond shape
- **Iris:** Frost cyan (#22D3EE)
- **Pupil:** Dark center with light reflection
- **Accent arcs:** Aurora purple (#A78BFA) above and below

This represents vision assistance while staying on-brand with Atlas Cortex.
