$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'Download-Recovery.ps1')
$python = 'D:\Anaconda\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Set $python to an existing Windows Python executable.' }
$lines = New-Object 'System.Collections.Generic.List[string]'
$log = { param($line) $lines.Add($line) }.GetNewClosure()
$expected = @('spaces here', 'embedded "quote"', 'G:\trailing\', '')
$result = Invoke-DownloadProcess -FilePath $python -NativeArguments (@('-I', '-B', '-c', 'import json,sys; print(json.dumps(sys.argv[1:]))') + $expected) -DriveProbe { $true } -Log $log
$actual = $lines[0] | ConvertFrom-Json
if ($result.Code -ne 0 -or $actual.Count -ne $expected.Count) { throw ('Argument round-trip failed: ' + ($result | ConvertTo-Json -Compress) + '; lines=' + ($lines | ConvertTo-Json -Compress)) }
for ($i=0; $i -lt $expected.Count; $i++) { if ($actual[$i] -cne $expected[$i]) { throw "Argument $i changed." } }
Write-Host 'PASS: stdout and Windows argument quoting'
$result = Invoke-DownloadProcess -FilePath $python -NativeArguments @('-I', '-B', '-c', 'import time; time.sleep(20)') -DriveProbe { $false } -Log $log
if ($result.Code -ne 75 -or $result.Reason -ne 'storage-unavailable') { throw 'Missing-drive detection failed.' }
Write-Host 'PASS: missing drive stops the owned client'
$result = Invoke-DownloadProcess -FilePath $python -NativeArguments @('-I', '-B', '-c', 'import time; time.sleep(20)') -DriveProbe { $true } -Log $log -QuietSeconds 1
if ($result.Code -ne 124 -or $result.Reason -ne 'unresponsive') { throw 'Quiet-timeout detection failed.' }
Write-Host 'PASS: stalled client times out'
$env:WSL_UTF8 = '1'
$lines.Clear()
$result = Invoke-DownloadProcess -FilePath (Join-Path $env:SystemRoot 'System32\wsl.exe') -NativeArguments @('--distribution', 'BrowserMeme-Ubuntu', '--user', 'research', '--exec', '/usr/bin/printf', '%s\n', 'WSL argument test') -DriveProbe { $true } -Log $log
if ($result.Code -ne 0 -or $lines[0] -ne 'WSL argument test') { throw 'WSL command-line round-trip failed.' }
Write-Host 'PASS: WSL command-line parsing'
