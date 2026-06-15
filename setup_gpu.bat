@echo off
chcp 65001 >nul
setlocal
rem all code lives in the app\ subfolder
cd /d "%~dp0app"

echo ============================================
echo  DragonMeow-MangaTranslator GPU setup
echo  (NVIDIA CUDA: torch cu126 + PaddleOCR + cudnn)
echo ============================================

if not exist .venv\Scripts\python.exe (
    echo [ERROR] .venv not found. Run setup.bat first, then run this again.
    pause
    exit /b 1
)

rem 委派給 setup_gpu.py —— 與 setup.bat 步驟 [2b] 完全相同的正確邏輯，可重複執行以修復／重裝：
rem   有 NVIDIA GPU → torch 2.7 cu126 + paddlepaddle-gpu 3.3.1 + nvidia-cudnn 9.23（覆蓋 torch\lib）
rem   不支援（GPU 太舊 / driver 不支援 cu126）→ 自動回退 CPU 版。
rem 注意：絕對不要在這裡自己 pip install torch（版本若與 setup_gpu.py 不一致會弄壞 cudnn → WinError 127）。
.venv\Scripts\python.exe setup_gpu.py

echo.
echo Done. Run start.bat to launch.
pause
