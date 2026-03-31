# Atlas Sight 👁️

**Offline Accessibility Assistant for Visually Impaired People**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](pyproject.toml)

---

## Why This Exists

There are roughly 40 million blind people in the world, and another 250 million
with moderate-to-severe vision loss. Most of them don't own flagship phones. Almost
none of them can afford monthly AI subscriptions. And yet every "AI vision assistant"
on the market requires a cloud connection, a modern iPhone, or both.

Atlas Sight exists because **accessibility shouldn't have a paywall**. It runs
entirely on-device — no internet, no accounts, no subscriptions, no cloud tokens,
no data leaving your phone, ever. A $200 Android phone or a Raspberry Pi is all
you need. You talk to it, it describes the world. That's the whole deal.

This is assistive technology for real people navigating real sidewalks, reading real
medicine labels, and asking for help in real emergencies. Every design decision —
from the tiny model sizes to the vibration patterns — was made with that person in
mind.

---

## How It Works

There is no visual interface. You don't need to see anything to use Atlas Sight.

You **talk** to it ("Hey Atlas, what do you see?"), **tap** the screen (double-tap
to describe, swipe to switch modes), or **shake** the phone for emergencies. It
responds with clear spoken descriptions, audio tones, and vibration patterns — all
designed to be understood without sight.

The camera sees the world. The AI describes it. You hear it. That's it.

### Voice Commands

Say **"Hey Atlas"** (or just **"Atlas"**) to wake it up, then speak a command:

| Command | What it does |
|---------|-------------|
| "What do you see?" / "Describe the scene" | Capture a frame and narrate what's visible |
| "Read the text" / "What does it say?" | Find and read aloud any visible text (signs, labels, menus) |
| "Where am I?" / "My location" | Announce compass heading, landmarks, and surroundings |
| "What's ahead?" / "Check for obstacles" | Scan for obstacles and report distances |
| "What is this?" / "Identify" | Describe the object you're pointing the camera at |
| "Start navigation" / "Guide me" | Switch to navigation mode with continuous obstacle warnings |
| "I need help" / "Emergency" / "SOS" | Activate emergency mode — detailed location + surroundings |
| "Remember this place" / "Bookmark" | Save the current scene and location for later |
| "Say that again" / "Repeat" | Replay the last spoken description |
| "More detail" / "Elaborate" | Switch to detailed descriptions |
| "Keep it brief" / "Be concise" | Switch to brief, one-sentence descriptions |
| "Speak louder" / "More volume" | Increase voice volume |
| "Speak softer" / "Quieter" | Decrease voice volume |
| "Speak faster" / "Speed up" | Increase speech speed |
| "Speak slower" / "Slow down" | Decrease speech speed |
| "Stop talking" / "Be quiet" | Silence current speech |

You can also say specific values: *"Set volume to 80"* or *"Set speed to 1.5"*.

### Gestures

Every gesture works by touch or motion — no need to look at the screen:

| Gesture | How | What it does |
|---------|-----|-------------|
| **Double-tap** | Tap twice quickly | Describe the current scene |
| **Swipe right** | Drag finger right | Read visible text |
| **Swipe left** | Drag finger left | Repeat last description |
| **Swipe up** | Drag finger up | More detail |
| **Swipe down** | Drag finger down | Switch to navigation mode |
| **Long press** | Hold finger ~1 second | Toggle continuous description on/off |
| **Two-finger tap** | Tap with two fingers | Identify the object in the center |
| **Shake** | Shake the phone firmly | **Emergency mode** — immediate location + surroundings |

### Audio Feedback

Atlas Sight uses distinct sounds so you always know what's happening:

| Sound | Meaning |
|-------|---------|
| **Short beep** (800 Hz) | Command acknowledged — working on it |
| **Rising chime** (two tones) | Text detected and ready to read |
| **Rising tone** (gets higher) | Obstacle getting closer — slow down |
| **Falling tone** (gets lower) | Obstacle receding — you're moving away from it |
| **Warning tone** (rising sweep) | Obstacle within 2 meters |
| **Pulsing alert** (rapid beeps) | **Danger** — obstacle within 0.8 meters, stop |
| **Three-note sweep** | Mode switched |
| **Falling tone** (low) | Error — something went wrong, will retry |

**Vibration patterns** reinforce the audio:

| Pattern | Meaning |
|---------|---------|
| Single short pulse | Command confirmed |
| Double pulse | Success / ready |
| Triple pulse (warning) | Obstacle warning |
| Rapid pulses (5×) | **Danger** — stop moving |
| Slow heartbeat | Continuous mode is active |
| Two gentle pulses | Navigation mode active |

---

## Interaction Modes

Atlas Sight has five modes, each optimized for a different situation:

### 🔍 Explore (Default)

Continuous environmental awareness. The camera captures frames at regular
intervals and describes what's around you — people, objects, changes in the scene.
Descriptions are deduplicated so you aren't told the same thing twice.

*Activated by: starting the app, or saying "Explore mode"*

### 📖 Read

Finds and reads text aloud — signs, labels, menus, medicine bottles, receipts.
Text is read top-to-bottom in natural reading order. You can ask for specific text:
*"Read the menu"* or *"What does the sign say?"*

*Activated by: swiping right, or saying "Read the text"*

### 🧭 Navigate

Guided walking with continuous obstacle detection. Announces compass heading,
warns about obstacles with escalating urgency (audio tones + vibration), and
lets you bookmark locations as landmarks.

*Activated by: swiping down, or saying "Start navigation"*

### 🔎 Identify

Point-and-ask mode. Hold an object up to the camera or point it at something
and ask *"What is this?"* — you'll get a focused description of that specific
object. Follow up with questions: *"Is this expired?"* or *"What color is it?"*

*Activated by: two-finger tap, or saying "Identify" / "What is this?"*

### 🆘 Emergency

Maximum-context awareness for when you need help. Combines compass heading,
detailed surroundings description, and nearby landmarks into a comprehensive
location report you can relay to someone over the phone.

*Activated by: shaking the phone, or saying "Emergency" / "I need help"*

---

## Technical Architecture

Atlas Sight is built in four layers that process input concurrently and
produce non-visual output:

```
┌──────────────────────────────────────────────────────┐
│                    SightEngine                        │
│          (async orchestrator, main loop)              │
├──────────────┬──────────────┬────────────┬───────────┤
│   Vision     │    Voice     │ Interaction│ Navigation│
│              │              │            │           │
│ • Camera     │ • Listener   │ • Gestures │ • Compass │
│ • VLM        │   (wake word │ • Haptics  │ • Obstacle│
│ • OCR        │    + STT)    │ • Audio    │   warnings│
│ • Detector   │ • Speaker    │   cues     │ • Landmark│
│              │   (TTS)      │            │   memory  │
│              │ • Command    │            │           │
│              │   parser     │            │           │
└──────────────┴──────────────┴────────────┴───────────┘
```

**Vision** captures camera frames and runs them through a tiny vision-language
model (VLM) for scene description, text reading (OCR), and object detection —
all from a single model, no separate OCR engine needed.

**Voice** listens for wake words, transcribes speech to text, parses commands
via fast pattern matching (no ML needed for intent recognition), and manages
a priority-queued text-to-speech output so urgent messages (like danger alerts)
interrupt less important ones.

**Interaction** handles touch gestures, vibration feedback, and synthesized
audio tones. All audio cues are generated mathematically (sine waves) — no
sound files to ship.

**Navigation** estimates object distances from bounding box sizes, classifies
obstacle severity, tracks compass heading, and manages user-bookmarked landmarks.

The **SightEngine** ties it all together: voice commands and gestures both
route through a unified dispatcher to the active mode, which coordinates the
appropriate subsystems and speaks the result.

### Design Principles

- **A blind person cannot see stack traces.** Every public method catches
  exceptions and speaks a human-friendly error message instead of crashing.
- **Concurrent, never blocking.** VLM inference and object detection run in
  parallel via `asyncio.gather`. Camera I/O runs in a thread pool. The event
  loop stays responsive to voice commands even during heavy computation.
- **Context-aware.** The VLM receives recent description history so it focuses
  on what *changed*, not what was already said.
- **Deduplication.** Jaccard word-overlap similarity prevents boring repetition
  of the same scene description.

### Memory Requirements

The entire system fits in ~1.1 GB of RAM:

| Component | Model | Size |
|-----------|-------|------|
| Vision-Language Model | Qwen3-VL-0.8B (Q4 quantized) | ~500 MB |
| Text-to-Speech | Piper | ~15 MB |
| Speech-to-Text | Whisper tiny | ~75 MB |
| Object detection | Shared with VLM | — |
| OCR | Shared with VLM | — |
| **Total** | | **~1.1 GB** |

No separate OCR engine or object detection model is needed — the VLM handles
scene description, text reading, and object identification through different
prompts.

---

## Quick Start

```bash
# Full install (vision + voice):
pip install atlas-sight[full]

# Or minimal (core only, no ML models):
pip install atlas-sight

# Run:
atlas-sight
```

Optional extras:
```bash
pip install atlas-sight[vision]   # Camera + VLM + detection
pip install atlas-sight[voice]    # Wake word + STT + TTS
```

---

## Development

```bash
git clone https://github.com/Betanu701/atlas-sight.git
cd atlas-sight
pip install -e ".[dev]"
python -m pytest tests/ -q
```

Tests use `pytest-asyncio` with `asyncio_mode = auto`.

---

## Project Structure

```
atlas-sight/
├── atlas_sight/
│   ├── __init__.py                 # Package version (0.1.0)
│   ├── config.py                   # SightConfig and all settings dataclasses
│   │
│   ├── core/                       # Orchestration
│   │   ├── engine.py               # SightEngine — main coordinator
│   │   ├── context.py              # ContextTracker — deduplication
│   │   └── scene.py                # SceneAnalyzer — vision fusion
│   │
│   ├── data/                       # Data models
│   │   ├── models.py               # BoundingBox, DetectedObject, Scene, etc.
│   │   └── history.py              # SessionHistory — rolling window + bookmarks
│   │
│   ├── interaction/                # User I/O
│   │   ├── gestures.py             # GestureHandler — touch & motion recognition
│   │   ├── haptics.py              # HapticFeedback — vibration patterns
│   │   └── audio_cues.py           # AudioCues — synthesized tones
│   │
│   ├── modes/                      # Interaction modes
│   │   ├── base.py                 # ModeBase (abstract)
│   │   ├── explore.py              # Continuous scene narration
│   │   ├── read.py                 # Text finding and reading
│   │   ├── navigate.py             # Obstacle-aware walking guidance
│   │   ├── identify.py             # Point-and-ask identification
│   │   └── emergency.py            # Emergency location awareness
│   │
│   ├── navigation/                 # Wayfinding
│   │   ├── orientation.py          # Compass, GPS, landmarks
│   │   └── obstacle.py             # Proximity alerts and severity
│   │
│   ├── vision/                     # Computer vision
│   │   ├── camera.py               # Async OpenCV frame capture
│   │   ├── vlm.py                  # Vision-language model (scene + QA)
│   │   ├── ocr.py                  # VLM-based text extraction
│   │   └── detector.py             # VLM-based object detection
│   │
│   └── voice/                      # Voice I/O
│       ├── commands.py             # CommandParser — intent matching
│       ├── speaker.py              # Priority-queued TTS
│       └── listener.py             # Wake word + STT
│
├── tests/                          # Test suite
├── pyproject.toml                  # Package configuration
├── pytest.ini                      # Test settings
└── README.md                       # You are here
```

---

## Configuration

All settings live in `SightConfig` (defined in `atlas_sight/config.py`):

```python
from atlas_sight.config import SightConfig, VoiceSettings, Verbosity, Mode

config = SightConfig(
    verbosity=Verbosity.NORMAL,       # BRIEF, NORMAL, or DETAILED
    initial_mode=Mode.EXPLORE,        # Starting mode

    voice=VoiceSettings(
        speed=1.0,                    # TTS speed (0.5–2.0)
        volume=0.8,                   # TTS volume (0.0–1.0)
        wake_words=["hey atlas", "atlas"],
        silence_timeout_sec=2.0,      # Stop listening after silence
    ),

    vision=VisionSettings(
        camera_index=0,               # OpenCV device index
        frame_width=640,
        frame_height=480,
        capture_interval_sec=0.5,     # Explore mode frame rate
        ocr_confidence_threshold=0.5,
        detection_confidence_threshold=0.4,
        max_image_size=448,           # Max VLM input dimension
    ),

    navigation=NavigationSettings(
        obstacle_warn_distance_m=2.0, # Warning at 2 meters
        obstacle_danger_distance_m=0.8, # Danger at 0.8 meters
        scan_interval_sec=0.3,
    ),

    audio_cues=AudioCueSettings(
        enabled=True,
        haptics_enabled=True,
    ),

    history=HistorySettings(
        max_entries=100,              # Rolling scene history
        max_bookmarks=50,             # Saved locations
        dedup_similarity_threshold=0.8,
    ),

    data_dir=Path.home() / ".atlas-sight",
)
```

---

## Privacy

**Everything runs on your device. Period.**

- No internet connection required or used
- No cloud APIs, no remote servers, no phone-home telemetry
- No user accounts, no sign-up, no subscriptions
- Your camera feed is processed locally and never stored permanently
- Scene descriptions stay in a rolling in-memory window, then they're gone
- No data leaves your phone — not to us, not to anyone

Your world is yours. We just help you see it.

---

## Contributing

Atlas Sight is an accessibility project. Contributions that make it work
better for real people are always welcome.

1. Fork the repo and create a feature branch
2. Write tests for new functionality
3. Run the test suite: `python -m pytest tests/ -q`
4. Submit a pull request with a clear description of what changed and why

**Priority areas:**
- Improving VLM description quality for common accessibility scenarios
- Better obstacle distance estimation
- Support for additional languages
- Testing on real Android devices and Raspberry Pi hardware
- Documentation improvements (especially for non-technical users)

---

## License

MIT — use it, modify it, ship it, give it away. If it helps someone see the
world a little better, that's all we ask.
