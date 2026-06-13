@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0."
title DragonMeow-MangaTranslator Update

echo ============================================
echo  DragonMeow-MangaTranslator  online update
echo  從 GitHub 抓最新程式碼 + 內建 Python，更新後可直接使用
echo  （保留 模型/.venv/.env/你的字型，只新增與覆蓋、不刪既有檔）
echo ============================================
echo.
echo  [!] Please CLOSE the app first.  請先關閉執行中的程式（start.bat 視窗）。
echo.
pause

set "REPO=DragonMeow1012/DragonMeow-MangaTranslator"
set "ZIPURL=https://github.com/%REPO%/archive/refs/heads/main.zip"
set "PYURL=https://github.com/%REPO%/releases/latest/download/python-portable-win-py312.zip"
set "TMP=%TEMP%\dmmt_update"
set "ZIP=%TEMP%\dmmt_update.zip"
set "PYZIP=%TEMP%\dmmt_python.zip"

echo [1/5] Downloading latest source ...  下載最新程式碼 ...
curl -L --fail -o "%ZIP%" "%ZIPURL%"
if errorlevel 1 (
    echo [ERROR] Download failed. Check your internet connection.  下載失敗，請檢查網路。
    pause
    exit /b 1
)

echo [2/5] Extracting ...  解壓 ...
if exist "%TMP%" rmdir /s /q "%TMP%"
mkdir "%TMP%"
tar -xf "%ZIP%" -C "%TMP%"
if errorlevel 1 (
    echo [ERROR] Extract failed.  解壓失敗。
    pause
    exit /b 1
)

set "SRC=%TMP%\DragonMeow-MangaTranslator-main"
if not exist "%SRC%\setup.bat" (
    echo [ERROR] Unexpected archive layout.  壓縮檔結構異常，請改用完整 release 重裝。
    pause
    exit /b 1
)

echo [3/5] Applying code update ...  套用程式更新（不動 模型/.venv/python/.env/字型）...
robocopy "%SRC%" "%CD%" /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 /XD "%CD%\.venv" "%CD%\app\.venv" "%CD%\python" "%CD%\app\models" "%CD%\app\fonts\user" /XF ".env" "VERSION" >nul
if errorlevel 8 (
    echo [ERROR] Copy failed.  覆蓋失敗，可能有檔案被占用，請先關閉程式再試。
    pause
    exit /b 1
)

echo [4/5] Checking bundled Python ...  檢查內建 Python ...
if exist "python\python.exe" (
    echo       OK: bundled Python present.  已有內建 Python。
) else (
    echo       Not found -- downloading portable Python ~23MB ...  未偵測到，下載內建 Python ...
    curl -L --fail -o "%PYZIP%" "%PYURL%" || ( echo [ERROR] Python download failed. 內建 Python 下載失敗。& pause & exit /b 1 )
    tar -xf "%PYZIP%" -C "." || ( echo [ERROR] Python extract failed. 解壓失敗。& pause & exit /b 1 )
    del "%PYZIP%" 2>nul
    if not exist "python\python.exe" ( echo [ERROR] python\python.exe still missing. 解壓後仍找不到。& pause & exit /b 1 )
    echo       OK: python\python.exe ready.  內建 Python 就緒。
)

rem 記錄更新到的版本（盡力而為，失敗不影響更新），讓程式內線上更新比對一致
powershell -NoProfile -Command "try { $s=(Invoke-RestMethod ('https://api.github.com/repos/%REPO%/commits/main') -Headers @{'User-Agent'='dmmt-update'}).sha; Set-Content -Path 'app\VERSION' -Value $s -NoNewline -Encoding ascii; Write-Host ('VERSION = ' + $s) } catch { Write-Host '(version stamp skipped)' }"

rem 清理暫存
rmdir /s /q "%TMP%" 2>nul
del "%ZIP%" 2>nul

echo [5/5] Finalizing ...  收尾 ...
if exist "app\.venv\Scripts\python.exe" (
    echo       Updating dependencies ...  更新相依套件 ...
    app\.venv\Scripts\python.exe -m pip install -r app\requirements.txt
    echo.
    echo ============================================
    echo  Update complete!  更新完成！  Run start.bat to launch.  執行 start.bat 啟動。
    echo ============================================
    pause
) else (
    echo       No .venv yet -- running setup.bat to finish install ...
    echo       尚無 .venv，接著自動執行 setup.bat 完成安裝 ...
    echo.
    call setup.bat
)
