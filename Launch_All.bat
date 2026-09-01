@echo off
setlocal
title ZERO- FLOW ENGINE (BOTH HALVES)
cls

echo =========================================================
echo  STARTING BOTH HALVES AS SEPARATE PROCESSES
echo =========================================================
echo.
echo    F5-F10 / Shift+F1-F3  dictation  (own window + tray icon)
echo    F4                    read aloud (own window + tray icon)
echo.
echo Starting a dictation silences the reader, and the reader
echo will not speak while the mic is open. Close either window
echo to stop that half.
echo.
echo For one window instead of two, use Launch_Zero.bat.
echo.

cd /d "%~dp0"

rem Keep this file pure ASCII with no labels - see the note in Launch_Zero.bat.
start "Zero- Flow - dictation" "%~dp0Launch_Flow.bat"
start "Zero- Flow - reader" "%~dp0Launch_Reader.bat"
