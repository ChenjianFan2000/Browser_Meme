@echo off
set "BM_SCRIPT_ROOT=%~dp0"
set "BM_MIRROR=cn"
if /i "%~1"=="official" set "BM_MIRROR=official"
cd /d "%SystemRoot%"
echo Preparing existing environments; downloads and logs remain on G:.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BM_SCRIPT_ROOT%research.ps1" -Action prepare -Profile all -Mirror %BM_MIRROR%
if errorlevel 1 goto failed
echo Download recovery enabled. Completed files are verified and reused.
echo Full site images require about 210 GB of downloads, plus extraction space.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BM_SCRIPT_ROOT%research.ps1" -Action download -Profile all -Mirror %BM_MIRROR%
if errorlevel 1 goto failed
echo Downloads completed. Run Install-All.cmd next.
pause
exit /b 0
:failed
echo Setup or download stopped after bounded retries. Partial files were retained.
echo Reconnect G: or restore the network, then rerun this script to resume.
echo See .runtime\logs\*-download-recovery.log and download-state.json.
pause
exit /b 1
