#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
#  Atlas Sight — Start Offline
#
#  Launches all services locally on the phone:
#    1. llama-server  (LLM on :8080)
#    2. whisper-server (STT on :10300) — optional
#    3. FastAPI server (Web UI on :5200)
#
#  Open Chrome → http://localhost:5200
# ============================================================================
set -e

SIGHT_DIR="$HOME/atlas-sight"
MODEL_DIR="$SIGHT_DIR/models"
LOG_DIR="$SIGHT_DIR/logs"
mkdir -p "$LOG_DIR"

# Paths
LLAMA_SERVER="$SIGHT_DIR/llama.cpp/build/bin/llama-server"
LLM_MODEL="$MODEL_DIR/qwen3.5-0.8b-q4_k_m.gguf"

# Whisper — check both possible locations
WHISPER_SERVER=""
for ws in \
    "$SIGHT_DIR/whisper.cpp/build/bin/whisper-server" \
    "$SIGHT_DIR/llama.cpp/build/bin/whisper-server"; do
    [ -f "$ws" ] && WHISPER_SERVER="$ws" && break
done
WHISPER_MODEL="$MODEL_DIR/ggml-tiny.en.bin"

DEMO_DIR="$SIGHT_DIR/demo"
# If demo files are in current directory, use that instead
[ -f "./server.py" ] && DEMO_DIR="$(pwd)"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║       Atlas Sight — Starting Up          ║"
echo "  ║       100% Offline • On-Device AI        ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ------------------------------------------------------------------
# Cleanup function
# ------------------------------------------------------------------
PIDS=""
cleanup() {
    echo ""
    echo "  Shutting down Atlas Sight..."
    for pid in $PIDS; do
        kill "$pid" 2>/dev/null && echo "  → Stopped PID $pid"
    done
    wait 2>/dev/null
    echo "  ✓ All services stopped"
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------------
# Verify prerequisites
# ------------------------------------------------------------------
if [ ! -f "$LLAMA_SERVER" ]; then
    echo "  ✗ llama-server not found at $LLAMA_SERVER"
    echo "    Run termux-setup.sh first!"
    exit 1
fi

if [ ! -f "$LLM_MODEL" ]; then
    echo "  ✗ LLM model not found at $LLM_MODEL"
    echo "    Run termux-setup.sh first!"
    exit 1
fi

# ------------------------------------------------------------------
# 1. Start llama-server (LLM)
# ------------------------------------------------------------------
echo "[1/3] Starting LLM server..."
echo "  Model: $(basename "$LLM_MODEL")"
echo "  Port:  8080"

"$LLAMA_SERVER" \
    --model "$LLM_MODEL" \
    --host 127.0.0.1 \
    --port 8080 \
    --ctx-size 2048 \
    --threads 4 \
    --batch-size 256 \
    --n-predict 512 \
    --flash-attn \
    > "$LOG_DIR/llama.log" 2>&1 &
LLAMA_PID=$!
PIDS="$PIDS $LLAMA_PID"

# Wait for llama-server to be ready
echo -n "  Waiting for LLM"
for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo ""
        echo "  ✓ LLM server ready (PID $LLAMA_PID)"
        break
    fi
    echo -n "."
    sleep 1
done
if ! curl -sf http://127.0.0.1:8080/health > /dev/null 2>&1; then
    echo ""
    echo "  ✗ LLM server failed to start. Check $LOG_DIR/llama.log"
    cat "$LOG_DIR/llama.log" | tail -20
    exit 1
fi
echo ""

# ------------------------------------------------------------------
# 2. Start whisper-server (STT) — optional
# ------------------------------------------------------------------
WHISPER_AVAILABLE=false
if [ -n "$WHISPER_SERVER" ] && [ -f "$WHISPER_SERVER" ] && [ -f "$WHISPER_MODEL" ]; then
    echo "[2/3] Starting Whisper STT server..."
    echo "  Model: $(basename "$WHISPER_MODEL")"
    echo "  Port:  10300"

    "$WHISPER_SERVER" \
        --model "$WHISPER_MODEL" \
        --host 127.0.0.1 \
        --port 10300 \
        --convert \
        > "$LOG_DIR/whisper.log" 2>&1 &
    WHISPER_PID=$!
    PIDS="$PIDS $WHISPER_PID"

    echo -n "  Waiting for Whisper"
    for i in $(seq 1 30); do
        if curl -sf http://127.0.0.1:10300/ > /dev/null 2>&1; then
            echo ""
            echo "  ✓ Whisper server ready (PID $WHISPER_PID)"
            WHISPER_AVAILABLE=true
            break
        fi
        echo -n "."
        sleep 1
    done
    if [ "$WHISPER_AVAILABLE" = false ]; then
        echo ""
        echo "  ⚠ Whisper didn't start — voice input will use browser STT"
    fi
else
    echo "[2/3] Whisper not available — voice input will use browser STT"
fi
echo ""

# ------------------------------------------------------------------
# 3. Start FastAPI server (Web UI)
# ------------------------------------------------------------------
echo "[3/3] Starting Atlas Sight web server..."
echo "  Port: 5200"

cd "$DEMO_DIR"

export LLAMA_HOST="127.0.0.1"
export LLAMA_PORT="8080"
export WHISPER_HOST="127.0.0.1"
export WHISPER_PORT="10300"
export SIGHT_PORT="5200"

python server.py &
SIGHT_PID=$!
PIDS="$PIDS $SIGHT_PID"

sleep 2
echo ""

# ------------------------------------------------------------------
# Ready!
# ------------------------------------------------------------------
echo "╔══════════════════════════════════════════════════╗"
echo "║            Atlas Sight is Running!               ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║  Open Chrome on this phone:                      ║"
echo "║  → http://localhost:5200                         ║"
echo "║                                                  ║"
echo "║  Services:                                       ║"
echo "║    LLM:     http://127.0.0.1:8080  ✓             ║"
if [ "$WHISPER_AVAILABLE" = true ]; then
echo "║    Whisper:  http://127.0.0.1:10300 ✓             ║"
else
echo "║    Whisper:  unavailable (browser STT fallback)  ║"
fi
echo "║    Web UI:   http://127.0.0.1:5200  ✓             ║"
echo "║                                                  ║"
echo "║  Airplane mode: YES ✈                            ║"
echo "║  Press Ctrl+C to stop all services               ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Keep running until interrupted
wait
