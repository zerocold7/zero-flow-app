@echo off
title ZERO- FLOW ENGINE (BOTH HALVES)
cls

echo =========================================================
echo 🚀 STARTING BOTH HALVES OF THE ZERO- FLOW ENGINE
echo =========================================================
echo.
echo    F5-F10 / Shift+F1-F3  dictation  (own window + tray icon)
echo    F4                    read aloud (own window + tray icon)
echo.
echo They coordinate over the microphone: starting a dictation
echo silences the reader, and the reader will not speak while
echo the mic is open. Close either window to stop that half.
echo.

cd /d "%~dp0"

start "Zero- Flow - dictation" "%~dp0Launch_Flow.bat"
start "Zero- Flow - reader" "%~dp0Launch_Reader.bat"
