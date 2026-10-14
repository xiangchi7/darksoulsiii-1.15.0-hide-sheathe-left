@echo off
rem One-click restore for HideSheathedLeft (DS3 1.15.0).
rem Double-click this file to put the backed-up originals back.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restore.ps1" %*
echo.
pause
