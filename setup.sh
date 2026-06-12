#!/usr/bin/env bash
# macOS / Linux 安裝腳本（對應 Windows 的 setup.bat）
# 用法：在終端機執行  bash setup.sh
set -e
cd "$(dirname "$0")/app"

echo "============================================"
echo " DragonMeow-MangaTranslator setup (macOS/Linux)"
echo "============================================"

# 優先找 3.11 / 3.10（其他版本不保證相容）
PY=""
for cand in python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "[ERROR] Python not found. Install Python 3.10 or 3.11 first:"
    echo "        https://www.python.org/downloads/  (or: brew install python@3.11)"
    exit 1
fi
echo "Using $($PY --version) ($PY)"
case "$($PY --version 2>&1)" in
    *" 3.10."*|*" 3.11."*) ;;
    *) echo "[WARN] Python 3.10/3.11 recommended; other versions may fail to install deps." ;;
esac

if [ ! -d .venv ]; then
    echo "[1/2] Creating virtual environment .venv ..."
    "$PY" -m venv .venv
else
    echo "[1/2] .venv already exists, skipping"
fi

echo "[2/2] Installing dependencies (first run takes several minutes) ..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env -- you can fill in GEMINI_API_KEY, or just paste the key in the web UI."
fi

echo
echo "Setup complete. Run:  bash start.sh"
