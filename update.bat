@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

rem Always run the real updater from a temporary copy.  This lets the update
rem safely replace update.bat itself while the temporary copy keeps running.
if /i "%~1"=="--worker" goto :worker
set "RUNNER=%TEMP%\dmmt_update_runner_%RANDOM%_%RANDOM%.bat"
copy /y "%~f0" "%RUNNER%" >nul
if errorlevel 1 (
    echo [ERROR] 無法建立暫存更新程式。
    pause
    exit /b 1
)
(
    call "%RUNNER%" --worker "%~dp0" %*
    set "UPDATE_RC=!errorlevel!"
    del "%RUNNER%" >nul 2>&1
    exit /b !UPDATE_RC!
)

:worker
set "ROOT=%~2"
if not defined ROOT (
    echo [ERROR] 找不到程式目錄。
    pause
    exit /b 1
)
for %%I in ("%ROOT%.") do set "ROOT=%%~fI\"
cd /d "%ROOT%"
title DragonMeow-MangaTranslator Updater
if /i "%~3"=="--self-test" (
    echo UPDATE_SELF_TEST_OK
    exit /b 0
)

set "REPO=DragonMeow1012/DragonMeow-MangaTranslator"
set "ZIPURL=https://github.com/%REPO%/archive/refs/heads/main.zip"
set "TMP=%TEMP%\dmmt_update_%RANDOM%_%RANDOM%"
set "ZIP=%TEMP%\dmmt_update_%RANDOM%_%RANDOM%.zip"

echo ============================================================
echo  DragonMeow-MangaTranslator 更新程式
echo ============================================================
echo  正在檢查 GitHub 最新版本...
echo.

set "LATEST="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Invoke-RestMethod 'https://api.github.com/repos/%REPO%/commits/main' -Headers @{'User-Agent'='dmmt-update'}).sha } catch { exit 1 }"`) do if not defined LATEST set "LATEST=%%A"
if not defined LATEST (
    echo [ERROR] 無法取得 GitHub 最新版本，請檢查網路連線後再試。
    pause
    exit /b 1
)

set "CURRENT_VERSION="
if exist "app\VERSION" set /p CURRENT_VERSION=<"app\VERSION"
set "CURRENT_GIT="
if exist ".git" for /f "delims=" %%A in ('git rev-parse HEAD 2^>nul') do if not defined CURRENT_GIT set "CURRENT_GIT=%%A"
set "CURRENT=%CURRENT_VERSION%"
if not defined CURRENT set "CURRENT=%CURRENT_GIT%"
if not defined CURRENT set "CURRENT=unknown"

if /i "%CURRENT_VERSION%"=="%LATEST%" goto :up_to_date
if /i "%CURRENT_GIT%"=="%LATEST%" goto :up_to_date
goto :update_available

:up_to_date
    echo [OK] 已是最新版本：%LATEST:~0,7%
    echo.
    pause
    exit /b 0

:update_available

echo 目前版本：%CURRENT:~0,7%
echo 最新版本：%LATEST:~0,7%
if exist ".git" (
    set "DIRTY="
    for /f "delims=" %%A in ('git status --porcelain 2^>nul') do set "DIRTY=1"
    if defined DIRTY echo [注意] 偵測到未提交修改；更新會覆蓋與新版同名的程式檔案。
)
echo.

for /l %%S in (5,-1,1) do (
    choice /C CN /N /T 1 /D N /M "[%%S] 秒後開始更新；按 C 取消... "
    if !errorlevel! equ 1 goto :cancelled
)

echo.
echo [1/5] 正在強制關閉現有 server 與翻譯 worker...
set "DMMT_UPDATE_ROOT=%ROOT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=[IO.Path]::GetFullPath($env:DMMT_UPDATE_ROOT).TrimEnd('\'); Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.IndexOf($root,[StringComparison]::OrdinalIgnoreCase) -ge 0 -and ($_.CommandLine -match 'server[\\/]main\.py' -or $_.CommandLine -match '-m\s+manga_translator\s+shared') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

echo [2/5] 正在下載最新程式碼...
curl -L --fail --silent --show-error -o "%ZIP%" "%ZIPURL%"
if errorlevel 1 goto :download_error

echo [3/5] 正在解壓縮...
mkdir "%TMP%" >nul 2>&1
tar -xf "%ZIP%" -C "%TMP%"
if errorlevel 1 goto :extract_error
set "SRC=%TMP%\DragonMeow-MangaTranslator-main"
if not exist "%SRC%\setup.bat" goto :layout_error

echo [4/5] 正在套用更新（保留模型、環境、設定與翻譯結果）...
robocopy "%SRC%" "%ROOT%." /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 ^
    /XD "%SRC%\.git" "%SRC%\.venv" "%SRC%\python" "%SRC%\app\.venv" "%SRC%\app\models" "%SRC%\app\result" "%SRC%\app\logs" "%SRC%\app\fonts\user" ^
    /XF ".env" "VERSION" "user_settings.json" "update.bat" >nul
set "COPY_RC=!errorlevel!"
if !COPY_RC! geq 8 goto :copy_error

set "DMMT_LATEST=%LATEST%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-Content -LiteralPath 'app\VERSION' -Value $env:DMMT_LATEST -NoNewline -Encoding ascii"

echo [5/5] 正在更新相依套件...
if exist "app\.venv\Scripts\python.exe" (
    "app\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "app\requirements.txt"
    if errorlevel 1 echo [WARN] 相依套件更新失敗；程式碼已更新，可稍後重新執行 setup.bat。
) else (
    echo [WARN] 尚未安裝 Python 環境；請在更新後執行 setup.bat。
)

rem This process is running from a temporary copy, so replacing update.bat is safe.
copy /y "%SRC%\update.bat" "%ROOT%update.bat" >nul
if errorlevel 1 echo [WARN] update.bat 本身未能更新；其餘程式碼已完成更新。
del "%ZIP%" >nul 2>&1
rmdir /s /q "%TMP%" >nul 2>&1

echo.
echo ============================================================
echo  更新完成：%LATEST:~0,7%
echo ============================================================
choice /C YN /N /M "是否立即啟動 server？[Y/N] "
if errorlevel 2 (
    echo 已完成更新，之後可執行 start.bat 開啟 server。
    pause
    exit /b 0
)
start "" "%ROOT%start.bat"
echo 已啟動 server。
timeout /t 2 /nobreak >nul
exit /b 0

:cancelled
echo.
echo 已取消更新，server 不會被關閉。
timeout /t 2 /nobreak >nul
exit /b 0

:download_error
echo [ERROR] 下載失敗，server 已關閉；請檢查網路後重新執行 update.bat。
goto :failed

:extract_error
echo [ERROR] 解壓縮失敗。
goto :failed

:layout_error
echo [ERROR] 下載內容格式不正確。
goto :failed

:copy_error
echo [ERROR] 複製程式碼失敗，robocopy code=!COPY_RC!。
goto :failed

:failed
del "%ZIP%" >nul 2>&1
if exist "%TMP%" rmdir /s /q "%TMP%" >nul 2>&1
echo 請修正問題後再次執行 update.bat。
pause
exit /b 1
