#!/usr/bin/env bash
# macOS / Linux 安裝腳本（對應 Windows 的 setup.bat）
# 用法：在終端機執行  bash setup.sh
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/app"

echo "============================================"
echo " DragonMeow-MangaTranslator setup (macOS/Linux)"
echo "============================================"

# macOS：本專案的 torch / paddlepaddle / rusty 套件只有 Apple Silicon (arm64) wheel；
# 且 rusty-manga-image-translator 0.12.1 的 mac wheel 需要 macOS 15+。先擋 Intel、提示舊系統，
# 否則使用者只會看到 pip 噴一長串「no matching distribution」摸不著頭緒。
if [ "$(uname)" = "Darwin" ]; then
    if [ "$(uname -m)" != "arm64" ]; then
        echo "[ERROR] macOS 版僅支援 Apple Silicon (M 系列)；偵測到 Intel ($(uname -m))，無法安裝。"
        echo "        macOS build supports Apple Silicon (arm64) only; Intel Macs are unsupported."
        exit 1
    fi
    macmajor="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
    if [ -n "$macmajor" ] && [ "$macmajor" -lt 15 ] 2>/dev/null; then
        echo "[WARN] 偵測到 macOS $(sw_vers -productVersion)；部分套件需 macOS 15 以上，安裝可能失敗。"
        echo "       Some packages need macOS 15+; install may fail on this version."
    fi
fi

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

echo "[2/3] Installing dependencies (first run takes several minutes) ..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "[3/3] Verifying model files (missing/corrupt ones are re-downloaded) ..."
.venv/bin/python download_models.py || echo "[WARN] 有模型未補齊；請檢查網路後重跑，或單獨執行：.venv/bin/python download_models.py"

if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env -- you can fill in GEMINI_API_KEY, or just paste the key in the web UI."
fi

echo
echo "Setup complete. Run:  bash start.sh"
