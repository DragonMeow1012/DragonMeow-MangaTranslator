@echo off
setlocal
rem all code lives in the app\ subfolder
cd /d "%~dp0app"

echo ============================================
echo  DragonMeow-MangaTranslator setup
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10 or 3.11 first:
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist .venv (
    echo [1/3] Creating virtual environment .venv ...
    python -m venv .venv
) else (
    echo [1/3] .venv already exists, skipping
)

echo [2/3] Installing dependencies (first run takes several minutes) ...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed. Check the messages above.
    pause
    exit /b 1
)

echo [3/3] (Recommended) Have an NVIDIA GPU? Double-click setup_gpu.bat
echo        after this finishes to install GPU acceleration.
echo.

if not exist .env (
    copy .env.example .env >nul
    echo Created .env -- open it and fill in your GEMINI_API_KEY!
)

echo Setup complete. Run start.bat to launch.
pause
