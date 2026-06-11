@echo off
setlocal
rem all code lives in the app\ subfolder
cd /d "%~dp0app"

if not exist .venv\Scripts\python.exe (
    echo [ERROR] Environment not installed. Run setup.bat first.
    pause
    exit /b 1
)

if not exist .env (
    echo [ERROR] .env not found. Copy .env.example to .env and fill in GEMINI_API_KEY.
    pause
    exit /b 1
)

if not exist logs mkdir logs

rem Force UTF-8 so Japanese/Chinese text in logs is readable
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem Auto-detect GPU: fall back to CPU mode if CUDA torch is not available
set GPU_FLAG=--use-gpu
.venv\Scripts\python.exe -c "import torch,sys;sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
if errorlevel 1 set GPU_FLAG=

cls
echo  ============================================
echo   DragonMeow-MangaTranslator
echo  ============================================
echo   Web UI : http://127.0.0.1:8501
echo   Log    : logs\server.log
echo  --------------------------------------------
echo   Starting... browser opens when ready.
echo   Close this window to stop the server.
echo  ============================================

start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 180;$i++){try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',8501);$c.Close();break}catch{Start-Sleep 1}};Start-Process 'http://127.0.0.1:8501'"

.venv\Scripts\python.exe server\main.py %GPU_FLAG% --start-instance --host 127.0.0.1 --port 8501 --nonce None > logs\server.log 2>&1

echo.
echo Server stopped. If this was unexpected, check logs\server.log
pause

