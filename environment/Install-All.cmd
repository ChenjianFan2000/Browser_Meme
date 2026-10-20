@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0research.ps1" -Action install -Profile all
if errorlevel 1 goto failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0research.ps1" -Action doctor
if errorlevel 1 goto failed
echo Installation and checks completed.
pause
exit /b 0
:failed
echo Installation or checks failed. See .runtime\logs.
pause
exit /b 1
