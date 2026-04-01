# Atlas Sight — Offline AI on Pixel 9

100% offline AI vision assistant. Runs entirely on the phone via Termux.
No cloud. No WiFi. No subscription.

## Setup (one time, ~15 min)

**1.** Install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/)
(NOT the Play Store — that version is broken)

**2.** Open Termux and paste:

```bash
pkg install -y git && git clone https://github.com/Digitalbrainstem/atlas-sight.git ~/atlas-sight && bash ~/atlas-sight/demo/setup-pixel.sh
```

**3.** Wait for downloads (~600MB) and llama.cpp build (~8 min).

## Run (anytime — works in airplane mode ✈)

```bash
cd ~/atlas-sight/demo && bash start.sh
```

Then open **Chrome** → `http://localhost:5200`

## Use it

| Gesture | Action |
|---------|--------|
| **Double-tap** | Capture → describe scene |
| **Long press** | Voice question → answer |
| **Swipe right** | Read text mode |
| **Swipe left** | Repeat last |
| **Swipe up/down** | Speech speed |
| **Shake** | Emergency "where am I?" |

## How it works

```
┌────────────── Pixel 9 ──────────────┐
│                                      │
│  Chrome (localhost:5200)             │
│  Camera + Web Speech TTS/STT        │
│         │                            │
│  Termux │                            │
│  ├── FastAPI server.py  (:5200)     │
│  └── llama-server       (:8080)     │
│      └── Qwen3-0.6B Q4  (~400MB)   │
│                                      │
│  RAM: ~800MB  •  Offline  •  Free   │
└──────────────────────────────────────┘
```

- **LLM:** Qwen3-0.6B Q4 via llama-server (built from source in Termux)
- **STT:** Chrome Web Speech API (offline with Android language pack)
- **TTS:** Chrome Web Speech API (built-in, instant)
- **Camera:** Chrome getUserMedia (rear camera)

## Files

| File | What |
|------|------|
| `setup-pixel.sh` | One-time setup (builds llama.cpp, downloads model) |
| `start.sh` | Start llama-server + web UI |
| `server.py` | FastAPI proxy (serves UI, routes to LLM) |
| `index.html` | Phone UI (camera, gestures, voice) |

## Offline speech tip

For STT to work offline, download the English speech pack:
**Settings → System → Languages → Speech → Download "English (US)"**

(Usually pre-installed on Pixel 9.)

## Troubleshooting

**"LLM not running" in Chrome:**
```bash
# Check if llama-server is healthy
curl http://localhost:8080/health
# Check logs
cat ~/atlas-sight/llama.log
```

**Build fails:** Try with fewer threads:
```bash
cd ~/atlas-sight/llama.cpp
cmake --build build -j2 --target llama-server
```
