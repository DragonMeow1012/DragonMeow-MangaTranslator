#!/usr/bin/env bash
# macOS / Linux 啟動腳本（對應 Windows 的 start.bat）
# 用法：在終端機執行  bash start.sh
set -e
cd "$(dirname "$0")/app"

if [ ! -x .venv/bin/python ]; then
    echo "[ERROR] Environment not installed. Run:  bash setup.sh"
    exit 1
fi
if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
fi

mkdir -p logs
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

# 自動偵測 GPU：Apple Silicon 走 MPS、NVIDIA 走 CUDA，否則 CPU
GPU_FLAG="--use-gpu"
if ! .venv/bin/python -c "import torch,sys;sys.exit(0 if (torch.cuda.is_available() or torch.backends.mps.is_available()) else 1)" >/dev/null 2>&1; then
    GPU_FLAG=""
fi

echo " ============================================"
echo "  DragonMeow-MangaTranslator"
echo " ============================================"
echo "  Web UI : http://127.0.0.1:8501"
echo "  Log    : app/logs/server.log"
echo "  GPU    : ${GPU_FLAG:-off (CPU mode)}"
echo " --------------------------------------------"
echo "  Starting... browser opens when ready."
echo "  Press Ctrl+C to stop the server."
echo " ============================================"

# 等 port 開好再開瀏覽器（macOS 用 open、Linux 用 xdg-open）
(
    for i in $(seq 1 180); do
        if (exec 3<>/dev/tcp/127.0.0.1/8501) 2>/dev/null; then
            exec 3>&- 3<&-
            if command -v open >/dev/null 2>&1; then open "http://127.0.0.1:8501"; \
            elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://127.0.0.1:8501"; fi
            break
        fi
        sleep 1
    done
) &

.venv/bin/python server/main.py $GPU_FLAG --start-instance --host 127.0.0.1 --port 8501 --nonce None 2>&1 | tee logs/server.log
