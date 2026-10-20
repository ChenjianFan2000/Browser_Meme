@echo off
setlocal
set "BM_SCRIPT_ROOT=%~dp0"
cd /d "%SystemRoot%"
echo Prepare, resume downloads and install the three research runtimes.
echo Domestic mirrors first, official fallback. Storage and caches stay on G:.
echo This entry does NOT download the approximately 210 GB of site images.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BM_SCRIPT_ROOT%Complete-Runtimes.ps1" -Mirror cn
if errorlevel 1 goto failed
echo Runtime installation and checks completed.
pause
exit /b 0
:failed
echo Stopped. Completed downloads were retained. Rerun this entry to resume.
echo See G:\Browser_Meme\.runtime\logs for details.
pause
exit /b 1
