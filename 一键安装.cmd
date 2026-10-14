@echo off
rem One-click install for HideSheathedLeft (DS3 1.15.0).
rem Double-click this file. It installs the 4 mod files AND patches every
rem character model in chr\*.chrbnd.dcx (dummy 382/383), so nothing else is needed.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
echo Finished. See README.md / 手动安装说明.txt for details.
pause
