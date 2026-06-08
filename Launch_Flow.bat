@echo off
title ZERO- FLOW ENGINE RUNNER
cls

echo =========================================================
echo 🎙️ STARTING LOCAL VOICE FLOW PIPELINE
echo =========================================================
echo.

cd /d "%~dp0"

:: 1. Portable Python
if exist ".\python_env\python.exe" (
    echo 📦 Portable Python environment detected.
    ".\python_env\python.exe" local_flow.py
    goto :end
)

:: 2. Virtual Env
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python local_flow.py
    goto :end
)

:: 3. Global System Python
echo ⚠️ Running global system Python.
python local_flow.py

:end
pause > nul