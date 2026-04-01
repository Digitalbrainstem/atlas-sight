# Atlas Sight — 100% Offline Phone Demo

AI vision assistant that runs **entirely on your phone**. No cloud. No WiFi.
No subscription. Just a phone helping someone see.

Everything runs locally in [Termux](https://termux.dev) on Android:
- **LLM:** Qwen3.5-0.8B via llama-server (~500MB model)
- **STT:** Whisper tiny.en via whisper-server (~75MB model)
- **TTS:** Browser speechSynthesis (built-in, instant)
- **UI:** Chrome on localhost

**Total download:** ~600MB (one-time setup)
**Runtime RAM:** ~1.1GB
**Works in airplane mode** after setup ✈

## Quick Start

### 1. Install Termux

Install **Termux from F-Droid** (NOT the Play Store — the Play Store version is
outdated and broken):

→ https://f-droid.org/packages/com.termux/

### 2. Clone and set up

Open Termux and run:

```bash
pkg install -y git
git clone https://github.com/Digitalbrainstem/atlas-sight.git
cd atlas-sight/demo
bash termux-setup.sh
```

This takes 10-20 minutes (downloads models, builds llama.cpp + whisper.cpp).

### 3. Start Atlas Sight

```bash
cd ~/atlas-sight/demo
bash start-offline.sh
```

### 4. Open in Chrome

Switch to Chrome and navigate to:

```
http://localhost:5200
```

Grant camera and microphone permissions when prompted.

### 5. Use it!

- **Double-tap** → capture scene → hear description
- **Long press** → speak a question → hear answer
- **Swipe right** → switch to "read text" mode
- **Swipe left** → repeat last description
- **Shake phone** → "where am I?" emergency mode

## Architecture

```
┌──────────────────── Pixel 9 ────────────────────┐
│                                                   │
│  Chrome Browser (localhost:5200)                  │
│  ┌─────────────────────────────────────────────┐  │
│  │  Camera  ←→  Touch Gestures  ←→  Browser TTS│  │
│  └────────────────────┬────────────────────────┘  │
│                       │ fetch()                    │
│  Termux               ▼                            │
│  ┌─────────────────────────────────────────────┐  │
│  │  FastAPI :5200  (server.py)                  │  │
│  │  ├── /describe  → llama-server              │  │
│  │  ├── /ask       → llama-server              │  │
│  │  ├── /transcribe → whisper-server           │  │
│  │  └── /health                                 │  │
│  ├─────────────────────────────────────────────┤  │
│  │  llama-server :8080  (Qwen3.5-0.8B Q4)     │  │
│  ├─────────────────────────────────────────────┤  │
│  │  whisper-server :10300  (tiny.en)           │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  Total RAM: ~1.1 GB   •   No network needed       │
└───────────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `termux-setup.sh` | One-time setup: install deps, build llama.cpp, download models |
| `start-offline.sh` | Start all services (llama + whisper + web server) |
| `server.py` | FastAPI server — proxies between browser and local AI |
| `index.html` | Self-contained phone UI (inline CSS+JS) |
| `start.sh` | Start only the web server (for dev or remote LLM) |
| `requirements.txt` | Python dependencies |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Phone UI |
| `POST` | `/describe` | Image → scene description via LLM |
| `POST` | `/ask` | Voice question → answer via LLM |
| `POST` | `/transcribe` | Audio blob → text via Whisper |
| `GET`  | `/health` | Service status (LLM + Whisper) |

## Configuration

Environment variables (all optional — defaults work for local Termux):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMA_HOST` | `127.0.0.1` | llama-server host |
| `LLAMA_PORT` | `8080` | llama-server port |
| `WHISPER_HOST` | `127.0.0.1` | whisper-server host |
| `WHISPER_PORT` | `10300` | whisper-server port |
| `SIGHT_PORT` | `5200` | Web UI port |

## Requirements

- **Phone:** Pixel 9 (or any Android with 8GB+ RAM)
- **App:** Termux from F-Droid
- **Browser:** Chrome for Android
- **Storage:** ~2GB free (models + binaries)
- **Network:** Only needed during initial setup

## STT Fallback

If Whisper isn't running, the UI automatically falls back to Chrome's built-in
Web Speech API for voice input. This requires an internet connection on most
Android devices (Google processes speech in the cloud). For true offline STT,
use the Whisper server via `start-offline.sh`.

## Troubleshooting

**"LLM not running" error:**
```bash
# Check if llama-server is running
curl http://localhost:8080/health
# If not, restart:
bash start-offline.sh
```

**Build fails in Termux:**
```bash
# Make sure you have enough storage (2GB+)
df -h ~
# Try building with fewer threads
cd ~/atlas-sight/llama.cpp
cmake --build build -j2
```

**Camera not working in Chrome:**
Chrome requires a "secure context" for camera access. `localhost` counts as
secure. If accessing from another device, use `--ssl` flag:
```bash
python server.py --ssl
```
