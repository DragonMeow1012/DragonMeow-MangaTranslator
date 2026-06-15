@echo off
chcp 65001 >nul
setlocal
rem repo root (this file's folder, with trailing backslash)
set "ROOT=%~dp0"
title DragonMeow-MangaTranslator setup

rem ================================================================
rem  Step 0: 先從 GitHub 抓最新程式碼，再進行安裝。
rem  re-entry (--updated) 或 --no-update 會跳過這段，避免無限迴圈。
rem ================================================================
if /i "%~1"=="--updated"   goto :after_update
if /i "%~1"=="--no-update" goto :after_update

echo ============================================
echo  DragonMeow-MangaTranslator setup
echo  [0/4] 從 GitHub 抓最新程式碼 ...  Fetching latest code ...
echo ============================================

set "REPO=DragonMeow1012/DragonMeow-MangaTranslator"
set "ZIPURL=https://github.com/%REPO%/archive/refs/heads/main.zip"
set "TMP=%TEMP%\dmmt_setup_update"
set "ZIP=%TEMP%\dmmt_setup_update.zip"

curl -L --fail -o "%ZIP%" "%ZIPURL%"
if errorlevel 1 (
    echo [WARN] 抓不到最新程式碼（可能離線）；改用現有檔案繼續安裝。
    echo        Could not fetch latest code; continuing with existing files.
    goto :after_update
)

if exist "%TMP%" rmdir /s /q "%TMP%"
mkdir "%TMP%"
tar -xf "%ZIP%" -C "%TMP%"
if errorlevel 1 (
    echo [WARN] 解壓最新程式碼失敗；改用現有檔案繼續安裝。
    goto :after_update
)

set "SRC=%TMP%\DragonMeow-MangaTranslator-main"
if not exist "%SRC%\setup.bat" (
    echo [WARN] 下載的壓縮檔結構異常；改用現有檔案繼續安裝。
    goto :after_update
)

rem 記錄更新到的版本（盡力而為；與 app 內線上更新比對一致）。robocopy 會 /XF 掉 VERSION，
rem 所以這裡先寫好就不會被覆蓋。
powershell -NoProfile -Command "try { $s=(Invoke-RestMethod ('https://api.github.com/repos/%REPO%/commits/main') -Headers @{'User-Agent'='dmmt-setup'}).sha; Set-Content -Path '%ROOT%app\VERSION' -Value $s -NoNewline -Encoding ascii } catch {}"

echo [*] 套用程式更新（保留 模型 / .venv / python / .env / 你的字型）...
robocopy "%SRC%" "%ROOT%." /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 /XD "%ROOT%.venv" "%ROOT%app\.venv" "%ROOT%python" "%ROOT%app\models" "%ROOT%app\fonts\user" /XF ".env" "VERSION" >nul
if errorlevel 8 (
    echo [WARN] 套用更新時有檔案被占用；改用現有檔案繼續安裝。
)

rem ---- 收尾並用「剛更新好的」setup.bat 重新進入（--updated 跳過本段）----
rem 註：到這裡為止 setup.bat 自己可能已被覆蓋，故立刻重新呼叫、不再讀舊內容。
rmdir /s /q "%TMP%" 2>nul
del "%ZIP%" 2>nul
call "%ROOT%setup.bat" --updated
exit /b %errorlevel%


:after_update
rem all code lives in the app\ subfolder
cd /d "%ROOT%app"

echo ============================================
echo  DragonMeow-MangaTranslator setup
echo ============================================

rem ---- 1. Pick a Python interpreter --------------------------------
rem Prefer the bundled portable Python so users don't need to install Python.
rem (download python-portable-win-py312.zip from the release page and unzip it
rem  into the project root so that python\python.exe sits next to setup.bat)
set "PY=%ROOT%python\python.exe"
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
    echo [1/4] Creating virtual environment .venv ...
    "%PY%" -m venv .venv
) else (
    echo [1/4] .venv already exists, skipping
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

echo [2/4] Installing dependencies (first run takes several minutes) ...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed. Check the messages above.
    pause
    exit /b 1
)

echo [2b/4] 偵測 GPU，自動選擇 GPU 版（torch cu126 + PaddleOCR GPU + cudnn）或 CPU 版 ...
.venv\Scripts\python.exe setup_gpu.py

echo [3/4] 檢查並補齊模型檔（缺損 / 損壞會自動重新下載並校驗）...
echo        Verifying model files (missing/corrupt ones are re-downloaded) ...
.venv\Scripts\python.exe download_models.py
if errorlevel 1 (
    echo [WARN] 有模型未能補齊；請檢查網路後重跑 setup.bat，或單獨執行：
    echo        .venv\Scripts\python.exe download_models.py
)

echo [4/4] GPU 已於 [2b] 自動偵測並安裝完成（NVIDIA 顯卡→GPU 版，否則 CPU 版）。
echo        日後驅動更新、或想重裝／修復 GPU 加速時，重跑 setup.bat 即可。
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
