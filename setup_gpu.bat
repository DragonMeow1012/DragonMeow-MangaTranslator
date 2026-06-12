@echo off
setlocal
rem all code lives in the app\ subfolder
cd /d "%~dp0app"

echo ============================================
echo  DragonMeow-MangaTranslator GPU setup
echo  (NVIDIA CUDA PyTorch)
echo ============================================

if not exist .venv\Scripts\python.exe (
    echo [ERROR] .venv not found. Run setup.bat first, then run this again.
    pause
    exit /b 1
)

where nvidia-smi >nul 2>nul
if errorlevel 1 (
    echo [WARN] nvidia-smi not found -- no NVIDIA GPU driver detected.
    echo        This installer is for NVIDIA GPUs only.
    set /p CONTINUE="Continue anyway? [y/N] "
    if /i not "%CONTINUE%"=="y" exit /b 1
)

echo Installing CUDA PyTorch (about 2.5 GB download, please wait) ...
.venv\Scripts\python.exe -m pip install torch==2.6.0 torchvision==0.21.0 --force-reinstall --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
    echo [ERROR] Installation failed. Check your network and the messages above.
    pause
    exit /b 1
)

echo.
echo Verifying GPU is visible to PyTorch ...
.venv\Scripts\python.exe -c "import torch; ok = torch.cuda.is_available(); print('CUDA available:', ok); print('GPU:', torch.cuda.get_device_name(0) if ok else 'none')"

echo.
echo GPU setup complete. Run start.bat to launch.
pause
