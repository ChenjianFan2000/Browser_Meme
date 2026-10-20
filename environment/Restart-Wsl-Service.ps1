#Requires -RunAsAdministrator
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetPathRoot($projectRoot) -ne 'G:\') { throw 'Run this script from G:.' }
$env:TEMP = Join-Path $projectRoot '.runtime\temp'
$env:TMP = $env:TEMP
$logPath = Join-Path $projectRoot ('.runtime\logs\wsl-service-recovery-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
Start-Transcript -LiteralPath $logPath
try {
    $service = Get-Service -Name WslService
    if ($service.Status -eq 'Running') { $service.Stop() }
    try { $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30)) }
    catch [System.ServiceProcess.TimeoutException] {
        # Recovery only: stop a stuck WSL service after its orderly stop timed out.
        # Run only when research jobs and other WSL sessions have been closed.
        $serviceRecord = Get-CimInstance Win32_Service -Filter "Name='WslService'"
        if ($serviceRecord.State -ne 'Stop Pending' -or $serviceRecord.ProcessId -eq 0) { throw }
        $serviceProcess = Get-Process -Id $serviceRecord.ProcessId
        if ($serviceProcess.ProcessName -ne 'wslservice') { throw 'Unexpected service process.' }
        Write-Host 'WSL service stop timed out; terminating its stalled service process.'
        Stop-Process -Id $serviceRecord.ProcessId -Force
    }
    Start-Service -Name WslService
    (Get-Service -Name WslService).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    Get-Service -Name WslService | Format-Table Name,Status
} finally { Stop-Transcript }
