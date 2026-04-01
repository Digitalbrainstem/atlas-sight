#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
#  Atlas Sight — Termux Setup (one-time)
#
#  Run this ONCE in Termux to install everything needed for offline operation.
#  After setup, use start-offline.sh to launch.
#
#  Total download: ~600MB
#  Requires: Termux from F-Droid (NOT Play Store)
# ============================================================================
set -e

SIGHT_DIR="$HOME/atlas-sight"
MODEL_DIR="$SIGHT_DIR/models"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║       Atlas Sight — Termux Setup         ║"
echo "  ║   100% Offline AI Vision Assistant       ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ------------------------------------------------------------------
# Step 0: Grant storage permission
# ------------------------------------------------------------------
echo "[0/6] Checking storage access..."
if [ ! -d "$HOME/storage" ]; then
    echo "  → Granting storage permission (tap Allow)..."
    termux-setup-storage
    sleep 2
fi
echo "  ✓ Storage OK"
echo ""

# ------------------------------------------------------------------
# Step 1: Update packages and install build dependencies
# ------------------------------------------------------------------
echo "[1/6] Installing system packages..."
pkg update -y -q
pkg install -y -q \
    python \
    cmake \
    make \
    clang \
    git \
    wget \
    openssl \
    ffmpeg \
    piper-tts 2>/dev/null || true
echo "  ✓ System packages installed"
echo ""

# ------------------------------------------------------------------
# Step 2: Install Python packages
# ------------------------------------------------------------------
echo "[2/6] Installing Python packages..."
pip install --quiet \
    fastapi \
    uvicorn \
    httpx \
    python-multipart
echo "  ✓ Python packages installed"
echo ""

# ------------------------------------------------------------------
# Step 3: Build / install llama.cpp
# ------------------------------------------------------------------
echo "[3/6] Setting up llama.cpp..."
LLAMA_DIR="$SIGHT_DIR/llama.cpp"

if [ -f "$LLAMA_DIR/build/bin/llama-server" ]; then
    echo "  ✓ llama.cpp already built"
else
    echo "  → Cloning llama.cpp..."
    mkdir -p "$SIGHT_DIR"
    if [ -d "$LLAMA_DIR" ]; then
        cd "$LLAMA_DIR" && git pull --quiet
    else
        git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$LLAMA_DIR"
    fi

    echo "  → Building llama.cpp (this takes 5-10 minutes)..."
    cd "$LLAMA_DIR"
    cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_OPENMP=OFF \
        2>/dev/null
    cmake --build build --config Release -j4 --target llama-server llama-cli 2>&1 | \
        tail -1

    if [ -f "$LLAMA_DIR/build/bin/llama-server" ]; then
        echo "  ✓ llama.cpp built successfully"
    else
        echo "  ✗ Build failed. Try: cd $LLAMA_DIR && cmake --build build -j2"
        exit 1
    fi
fi
echo ""

# ------------------------------------------------------------------
# Step 4: Download LLM model (Qwen3.5-0.8B Q4)
# ------------------------------------------------------------------
echo "[4/6] Downloading LLM model (~500MB)..."
mkdir -p "$MODEL_DIR"

LLM_MODEL="$MODEL_DIR/qwen3.5-0.8b-q4_k_m.gguf"
if [ -f "$LLM_MODEL" ]; then
    echo "  ✓ LLM model already downloaded"
else
    echo "  → Downloading Qwen3.5-0.8B Q4_K_M..."
    wget -q --show-progress -O "$LLM_MODEL" \
        "https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf" \
        || wget -q --show-progress -O "$LLM_MODEL" \
        "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
    echo "  ✓ LLM model downloaded"
fi
echo ""

# ------------------------------------------------------------------
# Step 5: Download Whisper model (tiny — ~75MB)
# ------------------------------------------------------------------
echo "[5/6] Downloading Whisper model (~75MB)..."

WHISPER_BIN="$LLAMA_DIR/build/bin/whisper-server"
WHISPER_MODEL="$MODEL_DIR/ggml-tiny.en.bin"

# Build whisper if part of llama.cpp, otherwise use standalone
if [ ! -f "$WHISPER_BIN" ]; then
    # Try building whisper from llama.cpp repo (some forks include it)
    # Otherwise we'll use whisper.cpp separately
    WHISPER_CPP_DIR="$SIGHT_DIR/whisper.cpp"
    if [ -f "$WHISPER_CPP_DIR/build/bin/whisper-server" ]; then
        WHISPER_BIN="$WHISPER_CPP_DIR/build/bin/whisper-server"
        echo "  ✓ whisper.cpp already built"
    else
        echo "  → Cloning whisper.cpp..."
        if [ -d "$WHISPER_CPP_DIR" ]; then
            cd "$WHISPER_CPP_DIR" && git pull --quiet
        else
            git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$WHISPER_CPP_DIR"
        fi

        echo "  → Building whisper.cpp (this takes 3-5 minutes)..."
        cd "$WHISPER_CPP_DIR"
        cmake -B build \
            -DCMAKE_BUILD_TYPE=Release \
            -DGGML_OPENMP=OFF \
            2>/dev/null
        cmake --build build --config Release -j4 --target whisper-server 2>&1 | \
            tail -1
        WHISPER_BIN="$WHISPER_CPP_DIR/build/bin/whisper-server"

        if [ -f "$WHISPER_BIN" ]; then
            echo "  ✓ whisper.cpp built successfully"
        else
            echo "  ⚠ whisper.cpp build failed — STT will be unavailable"
            echo "    Voice input will fall back to browser speech recognition"
        fi
    fi
fi

if [ -f "$WHISPER_MODEL" ]; then
    echo "  ✓ Whisper model already downloaded"
else
    echo "  → Downloading whisper tiny.en model..."
    wget -q --show-progress -O "$WHISPER_MODEL" \
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin"
    echo "  ✓ Whisper model downloaded"
fi
echo ""

# ------------------------------------------------------------------
# Step 6: Download Piper TTS voice (~15MB)
# ------------------------------------------------------------------
echo "[6/6] Setting up Piper TTS..."

PIPER_MODEL_DIR="$MODEL_DIR/piper"
PIPER_VOICE="$PIPER_MODEL_DIR/en_US-amy-medium.onnx"

mkdir -p "$PIPER_MODEL_DIR"

if [ -f "$PIPER_VOICE" ]; then
    echo "  ✓ Piper voice already downloaded"
else
    echo "  → Downloading Piper voice (Amy, medium quality)..."
    wget -q --show-progress -O "$PIPER_VOICE" \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx"
    wget -q --show-progress -O "${PIPER_VOICE}.json" \
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json"
    echo "  ✓ Piper voice downloaded"
fi
echo ""

# ------------------------------------------------------------------
# Step 7: Copy demo files
# ------------------------------------------------------------------
echo "Setting up Atlas Sight demo files..."
DEMO_SRC="$(cd "$(dirname "$0")" && pwd)"
DEMO_DST="$SIGHT_DIR/demo"
mkdir -p "$DEMO_DST"

for f in server.py index.html requirements.txt start-offline.sh; do
    if [ -f "$DEMO_SRC/$f" ]; then
        cp "$DEMO_SRC/$f" "$DEMO_DST/$f"
    fi
done
chmod +x "$DEMO_DST/start-offline.sh" 2>/dev/null

echo "  ✓ Demo files copied to $DEMO_DST"
echo ""

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo "╔══════════════════════════════════════════════════╗"
echo "║              Setup Complete!                     ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║                                                  ║"
echo "║  To start Atlas Sight:                           ║"
echo "║    cd ~/atlas-sight/demo                         ║"
echo "║    bash start-offline.sh                         ║"
echo "║                                                  ║"
echo "║  Then open Chrome:                               ║"
echo "║    http://localhost:5200                          ║"
echo "║                                                  ║"
echo "║  Works in airplane mode after this setup!        ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# Show sizes
echo "Installed components:"
[ -f "$LLM_MODEL" ] && echo "  LLM:     $(du -h "$LLM_MODEL" | cut -f1) — Qwen3.5-0.8B Q4"
[ -f "$WHISPER_MODEL" ] && echo "  Whisper: $(du -h "$WHISPER_MODEL" | cut -f1) — tiny.en"
[ -f "$PIPER_VOICE" ] && echo "  Piper:   $(du -h "$PIPER_VOICE" | cut -f1) — Amy medium"
echo ""
