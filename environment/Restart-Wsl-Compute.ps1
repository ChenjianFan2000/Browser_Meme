#Requires -RunAsAdministrator
# Recovery for this dedicated workstation; close WSL/container jobs before use.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:TEMP = Join-Path $projectRoot '.runtime\temp'
$env:TMP = $env:TEMP
$logPath = Join-Path $projectRoot '.runtime\logs\wsl-compute-recovery.log'
Start-Transcript -LiteralPath $logPath
try {
    foreach ($serviceName in @('WslService', 'vmcompute')) {
        $service = Get-Service -Name $serviceName
        if ($service.Status -eq 'Running') { $service.Stop() }
        try { $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30)) }
        catch [System.ServiceProcess.TimeoutException] {
            $record = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
            $process = Get-Process -Id $record.ProcessId
            if ($process.ProcessName -ne $serviceName) { throw 'Unexpected service process.' }
            Stop-Process -Id $record.ProcessId -Force
        }
    }
    Restart-Service -Name hns
} finally {
    Start-Service -Name vmcompute
    Start-Service -Name WslService
    Get-Service WslService,vmcompute,hns | Format-Table Name,Status
    Stop-Transcript
}
