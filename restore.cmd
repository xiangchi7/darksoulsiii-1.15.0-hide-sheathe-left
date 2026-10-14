@echo off
rem HideSheathedLeft 1.0.2 - one-click uninstall: puts the backed-up originals back.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restore.ps1" %*
echo.
pause
