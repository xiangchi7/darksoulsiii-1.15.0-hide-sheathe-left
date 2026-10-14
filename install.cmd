@echo off
rem HideSheathedLeft 1.0.1 - one-click install (payload + character-model patch).
rem Double-click this file. It copies the four mod files into the game folder AND
rem appends dummy 382/383 to every chr\*.chrbnd.dcx, so nothing else is needed.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
echo Finished. See README.md or docs\MANUAL-INSTALL.txt for details.
pause
