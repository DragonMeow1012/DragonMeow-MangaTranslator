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

rem 關閉 paddlepaddle 的 oneDNN（CPU 推論會炸 ConvertPirAttribute2RuntimeAttribute）。
rem 必須在 python 啟動前就設，否則 paddle 匯入後才設無效。
set FLAGS_use_mkldnn=0

rem 抹字長條全寬版每頁尺寸不一，CUDA caching allocator 容易碎裂、VRAM 一路爬高不釋放。
rem expandable_segments 讓配置器可伸縮段落、大幅降低碎裂（PyTorch 2.x；不支援的舊版/平台會自動忽略，無害）。
set PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

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

start "" /min powershell -NoProfile -WindowStyle Hidden -Command "$ok=$false;for($i=0;$i -lt 180;$i++){try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',8501);$c.Close();$ok=$true;break}catch{Start-Sleep 1}};if($ok){Start-Process 'http://127.0.0.1:8501'}"

.venv\Scripts\python.exe server\main.py %GPU_FLAG% --start-instance --host 127.0.0.1 --port 8501 --nonce None > logs\server.log 2>&1

echo.
echo Server stopped. If this was unexpected, check logs\server.log
pause

