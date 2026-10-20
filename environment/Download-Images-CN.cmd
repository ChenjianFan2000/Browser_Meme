@echo off
setlocal
set "BM_SCRIPT_ROOT=%~dp0"
cd /d "%SystemRoot%"
echo STEP 1: Download site images. After success, run Install-Images.cmd.
echo LARGE DOWNLOAD: site images require approximately 210 GB of network traffic.
echo GitLab uses a domestic mirror first, with official fallback.
echo The four frozen WebArena images use upstream Google Drive links.
echo No verified domestic source exists for those four archives.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BM_SCRIPT_ROOT%research.ps1" -Action prepare -Profile images -Mirror cn
if errorlevel 1 goto failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BM_SCRIPT_ROOT%research.ps1" -Action download -Profile images -Mirror cn
if errorlevel 1 goto failed
echo Image downloads completed. Run Install-Images.cmd to import them into Docker.
pause
exit /b 0
:failed
echo Stopped after bounded retries. Partial files were retained for resume.
echo See G:\Browser_Meme\.runtime\logs for details.
pause
exit /b 1
