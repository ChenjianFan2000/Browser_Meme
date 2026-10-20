[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 9337,
    [switch]$KeepAlive
)

$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$browserDirectory = Join-Path $projectDirectory '.runtime\phase1-browser'
$endpoint = "http://127.0.0.1:$Port/json/version"
try {
    $existing = Invoke-RestMethod -Uri $endpoint -TimeoutSec 2
    if ($existing.webSocketDebuggerUrl) {
        Write-Host "A Chrome debugging endpoint already exists at port $Port."
        Write-Host 'Use a different -Port if it is not the dedicated experiment browser.'
        exit 0
    }
} catch { }

$candidates = @(
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe')
)
$chromePath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chromePath) { throw 'Google Chrome was not found.' }

New-Item -ItemType Directory -Path $browserDirectory -Force | Out-Null
$profileDirectory = Join-Path $browserDirectory "profile-$Port"
$arguments = @(
    '--headless=new',
    '--disable-gpu',
    '--remote-debugging-address=127.0.0.1',
    "--remote-debugging-port=$Port",
    ('--user-data-dir="' + $profileDirectory + '"'),
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank'
)
$browserProcess = Start-Process -FilePath $chromePath -ArgumentList $arguments `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $browserDirectory "chrome-$Port.stdout.log") `
    -RedirectStandardError (Join-Path $browserDirectory "chrome-$Port.stderr.log")
$browserProcess.Id | Set-Content -LiteralPath (Join-Path $browserDirectory "chrome-$Port.pid") -Encoding ASCII
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $version = Invoke-RestMethod -Uri $endpoint -TimeoutSec 2
        if ($version.webSocketDebuggerUrl) {
            Write-Host "Dedicated experiment Chrome is ready: http://127.0.0.1:$Port"
            Write-Host "PID: $($browserProcess.Id); profile: $profileDirectory"
            if ($KeepAlive) {
                Write-Host 'Keeping the launcher alive for managed terminal process lifetime.'
                $misses = 0
                while ($misses -lt 3) {
                    Start-Sleep -Seconds 2
                    try {
                        $null = Invoke-RestMethod -Uri $endpoint -TimeoutSec 2
                        $misses = 0
                    } catch {
                        $misses++
                    }
                }
            }
            exit 0
        }
    } catch { }
}
throw "Chrome did not become ready. Inspect $browserDirectory."
