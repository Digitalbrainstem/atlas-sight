#!/bin/bash
# Start Atlas Sight demo
# Phone connects via local WiFi to this server
set -e

cd "$(dirname "$0")"

pip install -q --break-system-packages -r requirements.txt 2>/dev/null || pip install -q -r requirements.txt 2>/dev/null

LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "============================================"
echo "  Atlas Sight Demo"
echo "============================================"
echo ""
echo "  Open on phone: http://${LOCAL_IP}:5200"
echo ""
echo "  LLM backend:    http://192.168.3.8:8080"
echo "  Whisper STT:    http://192.168.3.8:10300"
echo "============================================"

python3 server.py
