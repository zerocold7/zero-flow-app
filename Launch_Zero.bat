@echo off
title ZERO- FLOW ENGINE
cls

echo =========================================================
echo 🚀 STARTING THE ZERO- FLOW ENGINE (single process)
echo =========================================================
echo.
echo    Dictation and read-aloud in one window, one tray icon.
echo    Whisper runs on the GPU; Kokoro runs on the CPU (required
echo    - see the note at the top of zero_flow.py).
echo.

cd /d "%~dp0"

:: 1. Portable Python
if exist ".\python_env\python.exe" (
    echo 📦 Portable Python environment detected.
    ".\python_env\python.exe" zero_flow.py
    goto :end
)

:: 2. Virtual Env
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python zero_flow.py
    goto :end
)

:: 3. Global System Python
echo ⚠️ Running global system Python.
python zero_flow.py

:end
pause > nul
