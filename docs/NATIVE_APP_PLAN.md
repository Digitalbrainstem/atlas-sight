# Atlas Sight — Native Android App Plan

> A voice-first accessibility app for visually impaired users.
> Fully offline. No cloud. No configuration. Works out of the box.

## Architecture: Local-First, Zero-Server

Everything runs on-device. No Atlas Cortex server required. No internet after
initial model download. This is critical — visually impaired users need this to
work at the grocery store, on the sidewalk, anywhere.

## Target

- **v1:** Personal use + sideload testing
- **v2:** Play Store distribution
- Package: `dev.atlascortex.sight`

---

## Tech Stack

| Component | Technology | Size | Why |
|-----------|-----------|------|-----|
| **Language** | Kotlin | — | Native Android, best accessibility API access |
| **UI Framework** | Jetpack Compose | — | Minimal visual UI, but needed for TalkBack integration |
| **Camera** | CameraX | — | Modern, lifecycle-aware, preview + capture |
| **VLM (Vision)** | Gemma 3n E4B via MediaPipe/LiteRT | ~1.5GB | Purpose-built for Android VLM, INT4, 3GB RAM, offline |
| **STT** | Sherpa-ONNX + Whisper small | ~200MB | Fully offline, Kotlin API, wake word support |
| **TTS** | Sherpa-ONNX + Piper voices | ~15MB | Offline, configurable speed, priority queue |
| **Gestures** | GestureDetector + SensorManager | — | Touch + accelerometer (shake) |
| **Haptics** | VibrationEffect API | — | Predefined patterns, no permissions on Android 13+ |
| **Audio Cues** | AudioTrack (PCM synthesis) | — | Sine wave tones, zero audio files shipped |
| **Total on-device** | | **~1.7GB** | Fits comfortably on any modern phone |

### Why Gemma 3n over Qwen-VL?

- Native Android `.task` bundle format (MediaPipe) — no custom inference code
- Google's LiteRT runtime optimized for Android GPU/NPU/CPU
- E4B variant: 4B effective params, runs on 3GB RAM with INT4
- Proven on-device VLM with image Q&A, scene description, OCR built-in
- Active community + Google support for edge deployment

### Why Sherpa-ONNX over Android SpeechRecognizer?

- Android's built-in STT requires Google Play Services (many phones don't have it)
- Sherpa-ONNX is truly offline — no hidden network calls
- Ships Whisper models (75MB-1.5GB, pick your quality/size tradeoff)
- Also provides offline TTS (Piper) — single dependency for all speech
- Kotlin API with AudioRecord integration examples
- Wake word detection built-in

---

## App Structure

```
dev.atlascortex.sight/
├── app/
│   ├── SightApplication.kt          # App init, model preloading
│   ├── MainActivity.kt              # Single activity, voice-first
│   └── ui/
│       ├── SightScreen.kt           # Minimal Compose UI (status + large buttons)
│       └── theme/Theme.kt           # High contrast, large text
│
├── core/
│   ├── SightEngine.kt               # Main orchestrator (binds all subsystems)
│   ├── ModeManager.kt               # 4-mode state machine + dispatcher
│   └── Config.kt                    # User preferences (speed, volume, verbosity)
│
├── vision/
│   ├── CameraManager.kt             # CameraX lifecycle, frame capture
│   ├── VisionModel.kt               # Gemma 3n via MediaPipe inference
│   ├── SceneDescriber.kt            # VLM prompting for scene descriptions
│   ├── TextReader.kt                # VLM-based OCR
│   └── ObjectDetector.kt            # VLM-based detection + distance estimation
│
├── voice/
│   ├── SpeechRecognizer.kt          # Sherpa-ONNX Whisper STT
│   ├── SpeechSynthesizer.kt         # Sherpa-ONNX Piper TTS + priority queue
│   ├── WakeWordDetector.kt          # "Hey Atlas" detection
│   └── CommandParser.kt             # 25+ voice intents, pattern matching
│
├── interaction/
│   ├── GestureHandler.kt            # 8 gesture types from touch + motion
│   ├── HapticEngine.kt              # Vibration patterns (acknowledge/warn/danger)
│   └── AudioCues.kt                 # Synthesized tones (beep/chime/warning/danger)
│
├── navigation/
│   ├── ObstacleWarner.kt            # Severity classification + directional warnings
│   └── OrientationHelper.kt         # Compass + landmark bookmarks
│
├── modes/
│   ├── ExploreMode.kt               # Continuous scene narration
│   ├── ReadMode.kt                  # Text reading (signs, menus, labels)
│   ├── NavigateMode.kt              # Obstacle scanning + compass
│   └── IdentifyMode.kt              # Point-and-ask object identification
│
├── data/
│   ├── Models.kt                    # Data classes: Scene, DetectedObject, Obstacle, etc.
│   ├── SessionHistory.kt            # Rolling scene window, bookmarks
│   └── ContextTracker.kt            # Deduplication (Jaccard similarity)
│
└── util/
    ├── ModelDownloader.kt           # First-run model download with voice progress
    └── Permissions.kt               # Camera + microphone permission flow (voice-guided)
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

### Phase 5: Polish + Distribution
- Context tracker (dedup repeated descriptions)
- Session history + bookmarks
- User preferences persistence
- Orientation/compass integration
- Play Store preparation (signing, listing, screenshots)
- Accessibility audit (TalkBack end-to-end testing)

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

- Android 13+ (API 33)
- 6GB+ RAM (3GB for VLM, 200MB STT, 15MB TTS, OS overhead)
- Camera (rear preferred, front fallback)
- Microphone
- ~2GB storage for models
- GPS + compass (optional, enhances navigation)

---

## Model Download Strategy

On first launch:
1. Speak: "Welcome to Atlas Sight. Downloading AI models. This only happens once."
2. Download Gemma 3n E4B `.task` bundle (~1.5GB) with voice progress every 25%
3. Download Sherpa-ONNX Whisper small model (~200MB)
4. Download Piper TTS voice (~15MB)
5. Speak: "Atlas Sight is ready. Double-tap or say Hey Atlas to begin."

Models stored in app-private storage. Re-download button in settings if corrupted.
Total first-download: ~1.7GB (one-time, cached forever).

---

## Eye Logo

The Atlas Sight icon is a stylized eye using Atlas brand colors:
- **Background:** Dark slate (#0F172A)
- **Eye:** White almond shape
- **Iris:** Frost cyan (#22D3EE)
- **Pupil:** Dark center with light reflection
- **Accent arcs:** Aurora purple (#A78BFA) above and below

This represents vision assistance while staying on-brand with Atlas Cortex.
