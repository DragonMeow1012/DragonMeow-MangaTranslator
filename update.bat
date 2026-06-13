@echo off
setlocal
cd /d "%~dp0."
title DragonMeow-MangaTranslator Update

echo ============================================
echo  DragonMeow-MangaTranslator  online update
echo  從 GitHub 抓最新程式碼覆蓋（保留 模型/.venv/python/設定/字型）
echo ============================================
echo.
echo  [!] Please CLOSE the app first.  請先關閉執行中的程式（start.bat 視窗）。
echo.
pause

set "REPO=DragonMeow1012/DragonMeow-MangaTranslator"
set "ZIPURL=https://github.com/%REPO%/archive/refs/heads/main.zip"
set "TMP=%TEMP%\dmmt_update"
set "ZIP=%TEMP%\dmmt_update.zip"

echo [1/4] Downloading latest source from GitHub ...
echo       下載最新程式碼 ...
curl -L --fail -o "%ZIP%" "%ZIPURL%"
if errorlevel 1 (
    echo [ERROR] Download failed. Check your internet connection.
    echo         下載失敗，請檢查網路連線後再試。
    pause
    exit /b 1
)

echo [2/4] Extracting ...  解壓 ...
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

echo [3/4] Applying update ...  套用更新（不動 模型/.venv/python/.env/你的字型）...
rem robocopy 只「新增/覆蓋」，沒有 /MIR /PURGE 不會刪除既有檔；排除大型與使用者私有資料夾/檔
robocopy "%SRC%" "%CD%" /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 /XD "%CD%\.venv" "%CD%\app\.venv" "%CD%\python" "%CD%\app\models" "%CD%\app\fonts\user" /XF ".env" "VERSION" >nul
rem robocopy 離開碼 0-7 = 成功，8 以上才是錯誤
if errorlevel 8 (
    echo [ERROR] Copy failed.  覆蓋失敗，可能有檔案被占用，請先關閉程式再試。
    pause
    exit /b 1
)

echo [4/4] Updating Python dependencies if needed ...  視需要更新相依套件 ...
if exist "app\.venv\Scripts\python.exe" (
    app\.venv\Scripts\python.exe -m pip install -r app\requirements.txt
) else (
    echo [!] .venv not found -- run setup.bat first.  找不到 .venv，請先執行 setup.bat。
)

rem 記錄這次更新到的版本（盡力而為，失敗不影響更新），讓程式內的線上更新比對保持一致
powershell -NoProfile -Command "try { $s=(Invoke-RestMethod ('https://api.github.com/repos/%REPO%/commits/main') -Headers @{'User-Agent'='dmmt-update'}).sha; Set-Content -Path 'app\VERSION' -Value $s -NoNewline -Encoding ascii; Write-Host ('VERSION = ' + $s) } catch { Write-Host '(version stamp skipped)' }"

rem 清理暫存
rmdir /s /q "%TMP%" 2>nul
del "%ZIP%" 2>nul

echo.
echo ============================================
echo  Update complete!  更新完成！
echo  Run start.bat to launch.  執行 start.bat 啟動。
echo ============================================
pause
