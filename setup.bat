@echo off
chcp 65001 >nul
setlocal
rem repo root (this file's folder, with trailing backslash)
set "ROOT=%~dp0"
title DragonMeow-MangaTranslator setup

rem ================================================================
rem  Step 0: fetch the latest code from GitHub, then install.
rem  re-entry (--updated) or --no-update skips this to avoid an endless loop.
rem ================================================================
if /i "%~1"=="--updated"   goto :after_update
if /i "%~1"=="--no-update" goto :after_update
if /i "%~1"=="--apply"     goto :apply_update

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

rem VERSION（版本號）改到 :apply_update 裡、robocopy 乾淨成功之後才寫（與 update.bat 一致），
rem 避免「半套更新卻把版本標成最新」騙過 app 內建的線上更新檢查。

rem ---- 加固自我更新：絕不在執行中覆蓋「正在跑的」setup.bat ----------------------------
rem cmd.exe 是按位元組位移讀 .bat 的；若 robocopy 在本檔執行到一半時把它換成長度不同的版本，
rem 後面幾行會錯位、可能爆掉。做法：先把「新版 setup.bat」複製成一個獨立檔 setup_new.bat，
rem 由它（而非正在跑的 setup.bat）去執行 robocopy 覆蓋，本檔就絕不會被「自己」覆蓋。
copy /y "%SRC%\setup.bat" "%ROOT%setup_new.bat" >nul
if errorlevel 1 (
    echo [WARN] 無法建立暫存更新器 setup_new.bat；改用現有檔案繼續安裝。
    goto :after_update
)
call "%ROOT%setup_new.bat" --apply "%SRC%"
set "RC=%errorlevel%"
rem 收尾清乾淨：下載暫存夾、zip、以及暫存更新器 → 資料夾回歸「乾淨的新版 setup.bat」。
rmdir /s /q "%TMP%" 2>nul
del "%ZIP%" 2>nul
del "%ROOT%setup_new.bat" >nul 2>nul
exit /b %RC%


:apply_update
rem 以 setup_new.bat 的身分執行（正在跑的不是 %ROOT%setup.bat），此時覆蓋 %ROOT%setup.bat 是安全的。
rem %~2 = 解壓出來的新原始碼資料夾(SRC)。
rem 注意：robocopy /XD 比對的是「來源端」目錄路徑，排除清單要用 %SRC%\... 而非目的端，否則排除不生效。
rem （那幾個資料夾本就被 .gitignore、不在 zip 裡，故即使排除失效目前也沒事；改用來源端是把保護做實、防未來。）
set "SRC=%~2"
set "REPO=DragonMeow1012/DragonMeow-MangaTranslator"
echo [*] 套用程式更新（保留 模型 / .venv / python / .env / 你的字型）...
robocopy "%SRC%" "%ROOT%." /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 /XD "%SRC%\.venv" "%SRC%\app\.venv" "%SRC%\python" "%SRC%\app\models" "%SRC%\app\fonts\user" /XF ".env" "VERSION" >nul
if errorlevel 8 (
    echo [WARN] 套用更新時有檔案被占用；本次不更新版本號，改用現有檔案繼續安裝。
    goto :apply_install
)
rem 只有 robocopy 乾淨成功（errorlevel 小於 8）才記錄版本號，避免半套更新騙過 app 線上更新檢查（與 update.bat 一致）。
powershell -NoProfile -Command "try { $s=(Invoke-RestMethod ('https://api.github.com/repos/%REPO%/commits/main') -Headers @{'User-Agent'='dmmt-setup'}).sha; Set-Content -Path '%ROOT%app\VERSION' -Value $s -NoNewline -Encoding ascii } catch {}"
:apply_install
rem 用「剛覆蓋好的新版」setup.bat 接手安裝（--updated 跳過 Step 0）。回到呼叫端後由它清掉 setup_new.bat。
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
    goto :have_python
)
where python >nul 2>nul
if not errorlevel 1 (
    set "PY=python"
    goto :have_python
)
rem No bundled and no system Python -- auto-download the portable build
rem (no pre-existing Python needed; uses the curl/tar built into Windows 10/11).
call :fetch_portable_python
if exist "%ROOT%python\python.exe" (
    set "PY=%ROOT%python\python.exe"
    goto :have_python
)
call :no_python
exit /b 1

:have_python

rem ---- make sure the interpreter actually runs ---------------------
rem (the "python" that opens the Microsoft Store passes "where python"
rem  but cannot run anything, so test it for real here)
"%PY%" -c "import sys" >nul 2>nul
if not errorlevel 1 goto :python_ok

rem The chosen interpreter cannot run -- on a fresh Windows 11 the "python"
rem on PATH is the Microsoft Store app-execution stub, which passes
rem "where python" yet cannot execute. Do NOT give up here: if we have not
rem already got a bundled portable Python, download one now and use it.
echo.
echo [*] 系統 Python 無法執行（多半是微軟商店捷徑），改用可攜版 ...
echo     System Python cannot run (likely the Microsoft Store stub); using portable ...
if not exist "%ROOT%python\python.exe" call :fetch_portable_python
if exist "%ROOT%python\python.exe" set "PY=%ROOT%python\python.exe"
"%PY%" -c "import sys" >nul 2>nul
if not errorlevel 1 goto :python_ok

echo.
echo [ERROR] Found Python but it cannot run.  /  找到 Python 但無法執行。
echo         This is usually the Microsoft Store stub.
echo         這通常是「微軟商店捷徑」而不是真正的 Python。
echo.
call :no_python
exit /b 1

:python_ok

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

rem ---- 1b. Microsoft Visual C++ runtime (torch/cuDNN load it at import) -----
call :ensure_vcredist

echo [2/4] Installing dependencies (first run takes several minutes) ...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed. Check the messages above.
    pause
    exit /b 1
)

echo [2b/4] 偵測 GPU，依顯卡自動選擇合適的 GPU 加速版或 CPU 版（torch / OCR / cuDNN 各挑對應版本）...
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

:fetch_portable_python
rem Auto-download the portable Python (python-build-standalone; same source/version as the release).
rem Windows 10/11 ships curl and tar, so even "no Python at all" can bootstrap one.
echo.
echo [*] No Python found -- auto-downloading portable Python 3.12 (~22 MB) ...
echo     找不到 Python，正在自動下載可攜版（約 22 MB）...
set "PYURL=https://github.com/astral-sh/python-build-standalone/releases/download/20260610/cpython-3.12.13%%2B20260610-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
set "PYTGZ=%TEMP%\dmmt_portable_py.tar.gz"
curl -L --fail -o "%PYTGZ%" "%PYURL%"
if errorlevel 1 (
    echo [WARN] 可攜 Python 下載失敗（可能離線、或無 curl）。改走手動提示。
    goto :eof
)
rem the tarball's top level is python\, so extracting to the project root just works
tar -xf "%PYTGZ%" -C "%ROOT%."
del "%PYTGZ%" 2>nul
if exist "%ROOT%python\python.exe" (
    echo [*] Portable Python ready. / 可攜 Python 已就緒。
) else (
    echo [WARN] 可攜 Python 解壓失敗（可能無 tar）。改走手動提示。
)
goto :eof

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

:ensure_vcredist
rem torch / cuDNN 在 import 時就會載入 Microsoft Visual C++ 執行階段；
rem 乾淨的 Windows 沒裝它，import torch 會以
rem   [WinError 126] 找不到指定的模組（或其相依）  失敗（常見於 cudnn*.dll）。
rem 同時檢查 vcruntime140_1.dll 與 msvcp140.dll：只看單一檔可能在「該檔在、但 msvcp140
rem 系列缺失/過舊」的機器上被誤判為已裝而跳過，仍然 import torch 失敗。兩者皆在才算 OK。
if exist "%SystemRoot%\System32\vcruntime140_1.dll" if exist "%SystemRoot%\System32\msvcp140.dll" goto :eof
echo.
echo [*] 未偵測到 Microsoft Visual C++ 執行階段（torch/cuDNN 需要），嘗試自動安裝 ...
echo     Microsoft Visual C++ runtime missing (torch/cuDNN need it); installing ...
set "VCR=%TEMP%\dmmt_vc_redist.x64.exe"
curl -L --fail -o "%VCR%" "https://aka.ms/vs/17/release/vc_redist.x64.exe"
if errorlevel 1 goto :vcr_warn
"%VCR%" /install /quiet /norestart
del "%VCR%" 2>nul
if exist "%SystemRoot%\System32\vcruntime140_1.dll" if exist "%SystemRoot%\System32\msvcp140.dll" (
    echo [*] VC++ 執行階段已安裝。 / VC++ runtime installed.
    goto :eof
)
:vcr_warn
echo.
echo [WARN] 無法自動安裝 VC++ 執行階段（可能需要系統管理員權限）。
echo        請手動下載安裝後再重跑 setup.bat： / Install manually, then re-run setup.bat:
echo        https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
goto :eof
