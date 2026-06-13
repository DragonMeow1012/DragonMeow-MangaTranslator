@echo off
setlocal
rem all code lives in the app\ subfolder
cd /d "%~dp0app"

echo ============================================
echo  DragonMeow-MangaTranslator setup
echo ============================================

rem ---- 1. Pick a Python interpreter --------------------------------
rem Prefer the bundled portable Python so users don't need to install Python.
rem (download python-portable-win-py312.zip from the release page and unzip it
rem  into the project root so that python\python.exe sits next to setup.bat)
set "PY=%~dp0python\python.exe"
if exist "%PY%" (
    echo [*] Using bundled portable Python.
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        call :no_python
        exit /b 1
    )
    set "PY=python"
)

rem ---- make sure the interpreter actually runs ---------------------
rem (the "python" that opens the Microsoft Store passes "where python"
rem  but cannot run anything, so test it for real here)
"%PY%" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Found Python but it cannot run.  /  找到 Python 但無法執行。
    echo         This is usually the Microsoft Store stub.
    echo         這通常是「微軟商店捷徑」而不是真正的 Python。
    echo.
    call :no_python
    exit /b 1
)

rem ---- 2. Create / repair the virtual environment ------------------
rem a leftover broken .venv from a previous failed run has no python.exe
if exist .venv if not exist ".venv\Scripts\python.exe" (
    echo [*] Removing a broken .venv from a previous attempt ...
    rmdir /s /q .venv
)

if not exist .venv (
    echo [1/3] Creating virtual environment .venv ...
    "%PY%" -m venv .venv
) else (
    echo [1/3] .venv already exists, skipping
)

rem venv MUST contain python.exe -- if not, creation failed; stop here
rem with a clear message instead of a misleading pip "path not found".
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] Virtual environment was not created.  /  虛擬環境建立失敗。
    echo         .venv\Scripts\python.exe is missing.
    echo.
    echo   Likely causes / 可能原因:
    echo     * the folder path has non-ASCII / special characters
    echo       資料夾路徑含中文或特殊字元 -- try moving it to e.g. C:\MangaTranslator
    echo     * antivirus blocked the bundled python.exe
    echo       防毒軟體擋下 python\python.exe -- right-click ^> Properties ^> Unblock
    echo.
    echo   Then delete the .venv folder and run setup.bat again.
    echo   接著刪掉 .venv 資料夾，重新執行 setup.bat。
    pause
    exit /b 1
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
exit /b 0

:no_python
echo [ERROR] No usable Python found.  /  找不到可用的 Python。
echo.
echo   Option A ^(easiest / 最簡單^): download "python-portable-win-py312.zip"
echo   from the release page and unzip it into this folder so that
echo   從 release 頁下載 python-portable-win-py312.zip，解壓到本資料夾，使得
echo       python\python.exe
echo   sits next to setup.bat, then run setup.bat again.
echo   與 setup.bat 同層，再重新執行 setup.bat。
echo.
echo   Option B: install Python 3.12 from https://www.python.org/downloads/
echo   安裝 Python 3.12，安裝時請勾選 "Add python.exe to PATH"。
pause
goto :eof
