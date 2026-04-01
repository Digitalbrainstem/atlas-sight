#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
#  Atlas Sight — Start
#
#  Starts llama-server + web UI server.
#  Open Chrome → http://localhost:5200
# ============================================================================
set -e

SIGHT_HOME="$HOME/atlas-sight"
LLAMA_SERVER="$SIGHT_HOME/llama.cpp/build/bin/llama-server"
MODEL_FILE="$SIGHT_HOME/models/qwen3-0.6b-q4_k_m.gguf"
DEMO_DIR="$SIGHT_HOME/demo"

# Allow running from the demo directory itself
[ -f "./server.py" ] && DEMO_DIR="$(pwd)"

echo ""
echo "  ╔═════════════════════════════════════╗"
echo "  ║   Atlas Sight — Starting            ║"
echo "  ╚═════════════════════════════════════╝"
echo ""

# ------------------------------------------------------------------
# Check prerequisites
# ------------------------------------------------------------------
if [ ! -f "$LLAMA_SERVER" ]; then
    echo "  ✗ llama-server not found"
    echo "    Run: bash setup-pixel.sh"
    exit 1
fi

if [ ! -f "$MODEL_FILE" ]; then
    # Try to find any .gguf file
    MODEL_FILE=$(find "$SIGHT_HOME/models" -name "*.gguf" -type f 2>/dev/null | head -1)
    if [ -z "$MODEL_FILE" ]; then
        echo "  ✗ No model file found"
        echo "    Run: bash setup-pixel.sh"
        exit 1
    fi
fi

# ------------------------------------------------------------------
# Cleanup on exit
# ------------------------------------------------------------------
PIDS=""
cleanup() {
    echo ""
    echo "  Stopping Atlas Sight..."
    for pid in $PIDS; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    echo "  Done."
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------------
# Start llama-server
# ------------------------------------------------------------------
echo "  Starting LLM ($(basename "$MODEL_FILE"))..."

"$LLAMA_SERVER" \
    --model "$MODEL_FILE" \
    --host 127.0.0.1 \
    --port 8080 \
    --ctx-size 2048 \
    --threads 4 \
    --batch-size 256 \
    --n-predict 512 \
    --flash-attn \
    > "$SIGHT_HOME/llama.log" 2>&1 &
LLAMA_PID=$!
PIDS="$LLAMA_PID"

# Wait for it
echo -n "  Waiting for LLM"
for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo " ✓"
        break
    fi
    echo -n "."
    sleep 1
done

if ! curl -sf http://127.0.0.1:8080/health > /dev/null 2>&1; then
    echo " ✗"
    echo "  Failed. Check: cat $SIGHT_HOME/llama.log"
    exit 1
fi

# ------------------------------------------------------------------
# Start web server
# ------------------------------------------------------------------
echo "  Starting web server..."

cd "$DEMO_DIR"
python server.py > "$SIGHT_HOME/sight.log" 2>&1 &
SIGHT_PID=$!
PIDS="$PIDS $SIGHT_PID"
sleep 2

echo ""
echo "  ╔═════════════════════════════════════╗"
echo "  ║   Atlas Sight is running!           ║"
echo "  ║                                     ║"
echo "  ║   Open Chrome:                      ║"
echo "  ║   http://localhost:5200             ║"
echo "  ║                                     ║"
echo "  ║   Ctrl+C to stop                    ║"
echo "  ╚═════════════════════════════════════╝"
echo ""

# Keep alive
wait
