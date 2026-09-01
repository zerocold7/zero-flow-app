@echo off
setlocal
title ZERO- FLOW ENGINE
cls

echo =========================================================
echo  STARTING THE ZERO- FLOW ENGINE (single process)
echo =========================================================
echo.
echo    Dictation and read-aloud in one window, one tray icon.
echo    Whisper runs on the GPU; Kokoro runs on the CPU.
echo    (Required - see the note at the top of zero_flow.py.)
echo.

cd /d "%~dp0"

rem Keep this file pure ASCII with no labels: cmd re-reads a batch file by byte
rem offset, and non-ASCII characters can desync that on some console codepages,
rem which silently eats the first word of later lines.
set "PY=python"
if exist "python_env\python.exe" set "PY=python_env\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

echo Using interpreter: %PY%
echo.
"%PY%" zero_flow.py

echo.
echo Engine stopped. Press any key to close this window.
pause > nul
