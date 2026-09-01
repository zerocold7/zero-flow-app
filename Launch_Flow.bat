@echo off
setlocal
title ZERO- FLOW ENGINE RUNNER
cls

echo =========================================================
echo  STARTING LOCAL VOICE FLOW PIPELINE
echo =========================================================
echo.

cd /d "%~dp0"

rem Keep this file pure ASCII with no labels - see the note in Launch_Zero.bat.
set "PY=python"
if exist "python_env\python.exe" set "PY=python_env\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

echo Using interpreter: %PY%
echo.
"%PY%" local_flow.py

echo.
echo Engine stopped. Press any key to close this window.
pause > nul
