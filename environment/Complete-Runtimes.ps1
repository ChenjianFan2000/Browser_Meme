[CmdletBinding()]
param([ValidateSet('cn', 'official')][string]$Mirror = 'cn')
$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot 'research.ps1'
Set-Location $env:SystemRoot
Write-Host "Preparing, downloading and installing research runtimes; source mode: $Mirror."
Write-Host 'Completed packages will be reused. Large site images are not included.'
foreach ($action in @('prepare', 'download', 'install')) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $entry -Action $action -Profile runtimes -Mirror $Mirror
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
Write-Host 'All three research runtimes are installed and checked. Site images are a separate download.'
