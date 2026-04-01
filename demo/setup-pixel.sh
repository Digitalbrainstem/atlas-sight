#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
#  Atlas Sight — Pixel 9 Setup
#
#  Paste this ONE command in Termux:
#    curl -sL https://raw.githubusercontent.com/Digitalbrainstem/atlas-sight/main/demo/setup-pixel.sh | bash
#
#  Or run it directly:
#    bash setup-pixel.sh
#
#  What it does:
#    1. Installs build tools (clang, cmake, python)
#    2. Builds llama.cpp from source (~8 min on Pixel 9)
#    3. Downloads Qwen3-0.6B Q4 model (~400MB)
#    4. Downloads Atlas Sight web UI files
#    5. Installs Python dependencies
#
#  Total: ~600MB download, ~15 min first time
#  After setup: works in airplane mode
# ============================================================================
set -e

SIGHT_HOME="$HOME/atlas-sight"
MODEL_DIR="$SIGHT_HOME/models"
LLAMA_DIR="$SIGHT_HOME/llama.cpp"

echo ""
echo "  ╔═════════════════════════════════════╗"
echo "  ║   Atlas Sight — Pixel 9 Setup       ║"
echo "  ║   100% Offline AI Vision Assistant  ║"
echo "  ╚═════════════════════════════════════╝"
echo ""

# ------------------------------------------------------------------
# 1. Install system packages
# ------------------------------------------------------------------
echo "[1/5] Installing packages..."
pkg update -y -q 2>/dev/null || true
pkg install -y clang cmake make git wget python 2>/dev/null
echo "  ✓ Packages installed"
echo ""

# ------------------------------------------------------------------
# 2. Build llama.cpp
# ------------------------------------------------------------------
echo "[2/5] Building llama.cpp..."

if [ -f "$LLAMA_DIR/build/bin/llama-server" ]; then
    echo "  ✓ Already built — skipping"
else
    mkdir -p "$SIGHT_HOME"
    if [ -d "$LLAMA_DIR" ]; then
        cd "$LLAMA_DIR" && git pull -q 2>/dev/null || true
    else
        echo "  → Cloning llama.cpp (shallow)..."
        git clone --depth 1 -q https://github.com/ggml-org/llama.cpp.git "$LLAMA_DIR"
    fi

    cd "$LLAMA_DIR"
    echo "  → Compiling (this takes ~8 minutes on Pixel 9)..."
    cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_OPENMP=OFF \
        -DLLAMA_CURL=OFF \
        2>/dev/null

    cmake --build build -j4 --target llama-server 2>&1 | tail -3

    if [ -f "$LLAMA_DIR/build/bin/llama-server" ]; then
        echo "  ✓ llama-server built"
    else
        echo "  ✗ Build failed. Try:"
        echo "    cd $LLAMA_DIR && cmake --build build -j2 --target llama-server"
        exit 1
    fi
fi
echo ""

# ------------------------------------------------------------------
# 3. Download model
# ------------------------------------------------------------------
echo "[3/5] Downloading LLM model (~400MB)..."
mkdir -p "$MODEL_DIR"

MODEL_FILE="$MODEL_DIR/qwen3-0.6b-q4_k_m.gguf"
if [ -f "$MODEL_FILE" ]; then
    echo "  ✓ Already downloaded — skipping"
else
    echo "  → Downloading Qwen3-0.6B Q4_K_M..."
    wget -q --show-progress \
        -O "$MODEL_FILE" \
        "https://huggingface.co/unsloth/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf" \
    || {
        echo "  → Primary download failed, trying fallback..."
        wget -q --show-progress \
            -O "$MODEL_FILE" \
            "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf"
    }
    echo "  ✓ Model downloaded"
fi
echo ""

# ------------------------------------------------------------------
# 4. Download Atlas Sight demo files
# ------------------------------------------------------------------
echo "[4/5] Downloading Atlas Sight UI..."
DEMO_DIR="$SIGHT_HOME/demo"
mkdir -p "$DEMO_DIR"

BASE_URL="https://raw.githubusercontent.com/Digitalbrainstem/atlas-sight/main/demo"

for f in server.py index.html requirements.txt start.sh; do
    echo "  → $f"
    wget -q -O "$DEMO_DIR/$f" "$BASE_URL/$f" 2>/dev/null || {
        # If wget fails (no internet?), check if file exists locally
        if [ -f "$(dirname "$0")/$f" ]; then
            cp "$(dirname "$0")/$f" "$DEMO_DIR/$f"
            echo "    (copied from local)"
        else
            echo "    ✗ Failed to download $f"
        fi
    }
done
chmod +x "$DEMO_DIR/start.sh"
echo "  ✓ UI files ready"
echo ""

# ------------------------------------------------------------------
# 5. Install Python packages
# ------------------------------------------------------------------
echo "[5/5] Installing Python packages..."
cd "$DEMO_DIR"
pip install -q fastapi uvicorn httpx python-multipart 2>/dev/null
echo "  ✓ Python packages installed"
echo ""

# ------------------------------------------------------------------
# Done!
# ------------------------------------------------------------------
echo "╔═══════════════════════════════════════════════╗"
echo "║            Setup Complete!                     ║"
echo "╠═══════════════════════════════════════════════╣"
echo "║                                               ║"
echo "║  To start:                                    ║"
echo "║    cd ~/atlas-sight/demo                      ║"
echo "║    bash start.sh                              ║"
echo "║                                               ║"
echo "║  Then open Chrome:                            ║"
echo "║    http://localhost:5200                       ║"
echo "║                                               ║"
echo "║  Works in airplane mode! ✈                    ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# Show what was installed
echo "Installed:"
[ -f "$LLAMA_DIR/build/bin/llama-server" ] && echo "  ✓ llama-server"
[ -f "$MODEL_FILE" ] && echo "  ✓ Model: $(du -h "$MODEL_FILE" | cut -f1)"
echo "  ✓ Web UI: $DEMO_DIR"
echo ""
