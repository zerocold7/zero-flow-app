@echo off
setlocal
title ZERO- FLOW READER
cls

echo =========================================================
echo  STARTING ZERO- FLOW READER (text to speech)
echo =========================================================
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
"%PY%" -m reader
set "CODE=%ERRORLEVEL%"

rem Started hidden (the .vbs launchers pass silent): never wait for a key, or
rem the hidden window would stay open, invisible, until the next sign-in.
if /i "%~1"=="silent" exit /b %CODE%
if "%CODE%"=="0" exit /b 0

echo.
echo Reader stopped with an error (exit code %CODE%). Details are in reader_debug.log.
echo Press any key to close this window.
pause > nul
exit /b %CODE%
