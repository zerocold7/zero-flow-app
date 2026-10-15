@echo off
setlocal
title ZERO- FLOW ENGINE RUNNER
cls

echo =========================================================
echo  STARTING THE ZERO- FLOW DICTATION HALF
echo =========================================================
echo.

cd /d "%~dp0"

rem Keep this file pure ASCII with no labels - see the note in Launch_Zero.bat.
set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

echo Using interpreter: %PY%
echo.
"%PY%" local_flow.py
set "CODE=%ERRORLEVEL%"

rem Started hidden (the .vbs launchers pass silent): never wait for a key, or
rem the hidden window would stay open, invisible, until the next sign-in.
if /i "%~1"=="silent" exit /b %CODE%
if "%CODE%"=="0" exit /b 0

echo.
echo Engine stopped with an error (exit code %CODE%). Details are in flow_debug.log.
echo Press any key to close this window.
pause > nul
exit /b %CODE%
