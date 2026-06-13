#!/usr/bin/env bash
# macOS / Linux 安裝腳本（對應 Windows 的 setup.bat）
# 用法：在終端機執行  bash setup.sh
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/app"

echo "============================================"
echo " DragonMeow-MangaTranslator setup (macOS/Linux)"
echo "============================================"

# macOS：清除下載 zip 帶來的隔離屬性，否則 Gatekeeper 會擋未簽章的內建 Python（執行時直接被 kill）。
if [ "$(uname)" = "Darwin" ] && [ -d "$ROOT/python" ]; then
    xattr -dr com.apple.quarantine "$ROOT/python" 2>/dev/null || true
fi

# 優先用內建可攜式 Python（解壓 portable python 後出現 python/bin/python3），
# 用戶就不必自己安裝 Python。先確認它真的能執行（架構不符時自動跳過、退回系統 Python）。
PY=""
# 先試真正的執行檔再試 symlink（避免依賴 symlink 在解壓時是否被還原）
for cand in "$ROOT/python/bin/python3.12" "$ROOT/python/bin/python3"; do
    if [ -x "$cand" ] && "$cand" --version >/dev/null 2>&1; then
        PY="$cand"
        echo "Using bundled portable Python ($("$PY" --version))"
        break
    fi
done
if [ -z "$PY" ]; then
    for cand in python3.12 python3.11 python3.10 python3; do
        if command -v "$cand" >/dev/null 2>&1; then
            PY="$cand"
            break
        fi
    done
fi
if [ -z "$PY" ]; then
    echo "[ERROR] No Python found. Unzip the portable Python into this folder"
    echo "        (so that python/bin/python3 exists), or install Python 3.12:"
    echo "        https://www.python.org/downloads/  (or: brew install python@3.12)"
    exit 1
fi
echo "Using $("$PY" --version) ($PY)"
case "$("$PY" --version 2>&1)" in
    *" 3.10."*|*" 3.11."*|*" 3.12."*) ;;
    *) echo "[WARN] Python 3.10/3.11/3.12 recommended; other versions may fail to install deps." ;;
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
