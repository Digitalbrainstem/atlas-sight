#!/bin/bash
# Start Atlas Sight demo server
# For offline Termux use: start-offline.sh (launches all services)
# This script starts only the FastAPI web server.
set -e

cd "$(dirname "$0")"

pip install -q --break-system-packages -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt 2>/dev/null

LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")

echo "============================================"
echo "  Atlas Sight"
echo "============================================"
echo ""
echo "  Local:  http://localhost:5200"
echo "  LAN:    http://${LOCAL_IP}:5200"
echo ""
echo "  LLM:    http://${LLAMA_HOST:-127.0.0.1}:${LLAMA_PORT:-8080}"
echo "  Whisper: http://${WHISPER_HOST:-127.0.0.1}:${WHISPER_PORT:-10300}"
echo "============================================"

python3 server.py "$@" || python server.py "$@"
