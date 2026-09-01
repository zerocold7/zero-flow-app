@echo off
title ZERO- FLOW READER RUNNER
cls

echo =========================================================
echo 🔊 STARTING ZERO- FLOW READER (text to speech)
echo =========================================================
echo.

cd /d "%~dp0"

:: 1. Portable Python
if exist ".\python_env\python.exe" (
    echo 📦 Portable Python environment detected.
    ".\python_env\python.exe" -m reader
    goto :end
)

:: 2. Virtual Env
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    python -m reader
    goto :end
)

:: 3. Global System Python
echo ⚠️ Running global system Python.
python -m reader

:end
pause > nul
