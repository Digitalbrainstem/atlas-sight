# Atlas Sight — Phone Demo

A web-based assistive vision demo. The phone captures images via camera and sends
them to the LLM running on Overwatch for scene description. Designed for visually
impaired users — all interaction is via touch gestures and voice.

## Quick Start

```bash
cd demo
pip install -r requirements.txt
python server.py
# Open on phone: http://<your-ip>:5200
```

Or use the start script:

```bash
chmod +x start.sh
./start.sh
```

## Architecture

```
Phone (Pixel 9)                    Blue (this machine)         Overwatch
┌─────────────┐   HTTP POST    ┌─────────────────┐  proxy  ┌──────────────┐
│ Chrome       │ ──────────▶   │ FastAPI :5200    │ ──────▶ │ llama-server │
│ Camera + Mic │               │ demo/server.py   │         │ :8080        │
│ TTS + STT    │ ◀──────────   │                  │ ◀────── │ Qwen3.5-0.8B │
└─────────────┘   JSON resp    └─────────────────┘         └──────────────┘
```

## Endpoints

| Method | Path        | Description                                    |
|--------|-------------|------------------------------------------------|
| GET    | `/`         | Serves the single-page HTML UI                 |
| POST   | `/describe` | Receives base64 image, returns text description|
| POST   | `/ask`      | Text question + optional image context → answer|
| GET    | `/health`   | Server health check                            |

## Phone Gestures

| Gesture          | Action                                 |
|------------------|----------------------------------------|
| Double-tap       | Capture image → describe scene         |
| Long press+speak | Voice question → get answer            |
| Swipe right      | Switch to "read text" mode             |
| Swipe left       | Repeat last description                |
| Shake device     | "Where am I?" emergency description    |

## Configuration

Environment variables:

- `LLAMA_HOST` — llama-server host (default: `192.168.3.8`)
- `LLAMA_PORT` — llama-server port (default: `8080`)
- `SIGHT_PORT` — demo server port (default: `5200`)

## Camera Access on Phone

Chrome allows camera access over HTTP for local network IPs (e.g., `192.168.x.x`).
If you need HTTPS, generate a self-signed certificate:

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=atlas-sight"
python server.py --ssl
```

## Requirements

- Python 3.11+
- Phone: Chrome on Android (tested on Pixel 9)
- LLM: llama-server running on Overwatch with a capable model
- Network: Phone and server on the same WiFi network
