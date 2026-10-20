@echo off
setlocal
set "BM_SCRIPT_ROOT=%~dp0"
cd /d "%SystemRoot%"
echo STEP 2: Import images after Download-Images-CN.cmd has completed successfully.
echo Complete-Runtimes-CN.cmd does not download site images.
echo Importing verified local image archives into Docker. No downloads are started.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BM_SCRIPT_ROOT%research.ps1" -Action install -Profile images
if errorlevel 1 goto failed
echo Images imported. See README.md for site startup commands.
pause
exit /b 0
:failed
echo Import failed. See the error above and G:\Browser_Meme\.runtime\logs.
echo If archives are missing or unverified, run Download-Images-CN.cmd first.
pause
exit /b 1
