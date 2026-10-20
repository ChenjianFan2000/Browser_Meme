#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$startInfo = [Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = "$env:SystemRoot\System32\wsl.exe"
$startInfo.Arguments = '--debug-shell'
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardInput = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true
$process = [Diagnostics.Process]::Start($startInfo)
$output = $process.StandardOutput.ReadToEndAsync()
$errors = $process.StandardError.ReadToEndAsync()
$process.StandardInput.Write("uname -a`ncat /proc/uptime`nps -ef`ndmesg | tail -n 100`ncat /proc/mounts`nexit`n")
$process.StandardInput.Close()
$process.WaitForExit()
[IO.File]::WriteAllText((Join-Path $projectRoot '.runtime\logs\wsl-boot-debug.log'), $output.Result + $errors.Result)
$process.Dispose()
