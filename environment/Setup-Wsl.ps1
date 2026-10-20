[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$distroName = 'BrowserMeme-Ubuntu'
$distroRoot = Join-Path $runtimeRoot 'wsl\Ubuntu-24.04'
if ([IO.Path]::GetPathRoot($projectRoot) -ne 'G:\') {
    throw 'This setup must run from the project on G:.'
}
foreach ($relativePath in @('downloads', 'temp', 'logs', 'wsl', 'cache')) {
    New-Item -ItemType Directory -Path (Join-Path $runtimeRoot $relativePath) -Force | Out-Null
}
$env:TEMP = Join-Path $runtimeRoot 'temp'
$env:TMP = $env:TEMP

function Invoke-WslControl {
    param([string]$Arguments)
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = "$env:SystemRoot\System32\wsl.exe"
    $startInfo.Arguments = $Arguments
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.EnvironmentVariables['WSL_UTF8'] = '1'
    $startInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
    $startInfo.StandardErrorEncoding = [Text.Encoding]::UTF8
    $process = [Diagnostics.Process]::Start($startInfo)
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    $errorTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $result = [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = $outputTask.Result
        Error = $errorTask.Result
    }
    $process.Dispose()
    return $result
}

# This small Windows configuration file is required to move WSL swap off C:.
# Keep all backups and every large/new runtime artifact under the G: project.
$wslConfigPath = Join-Path $env:USERPROFILE '.wslconfig'
$utf8 = [Text.UTF8Encoding]::new($false)
$configText = if (Test-Path -LiteralPath $wslConfigPath) {
    [IO.File]::ReadAllText($wslConfigPath)
} else { '' }
$originalConfig = $configText
$configValues = [ordered]@{
    memory = '10GB'
    processors = '8'
    swap = '4GB'
    swapFile = ((Join-Path $runtimeRoot 'wsl\swap.vhdx') -replace '\\', '\\')
    guiApplications = 'false'
    maxCrashDumpCount = '0'
    autoProxy = 'false'
}
if ($configText -notmatch '(?m)^\[wsl2\]\s*$') {
    $configText = $configText.TrimEnd() + "`r`n[wsl2]`r`n"
}
$sectionRegex = [regex]::new('(?ms)^\[wsl2\][ \t]*\r?\n(?<body>.*?)(?=^\[|\z)')
$sectionMatch = $sectionRegex.Match($configText)
$sectionBody = $sectionMatch.Groups['body'].Value
foreach ($configKey in $configValues.Keys) {
    $linePattern = '(?im)^' + [regex]::Escape($configKey) + '[ \t]*=.*$'
    $line = $configKey + '=' + $configValues[$configKey]
    if ($sectionBody -match $linePattern) {
        $replacementLine = $line
        $sectionBody = [regex]::Replace($sectionBody, $linePattern, [Text.RegularExpressions.MatchEvaluator]{ param($match) $replacementLine })
    } else { $sectionBody = $sectionBody.TrimEnd() + "`r`n" + $line + "`r`n" }
}
$replacementSection = "[wsl2]`r`n" + $sectionBody.TrimStart("`r", "`n") + "`r`n"
$configText = $sectionRegex.Replace($configText, [Text.RegularExpressions.MatchEvaluator]{ param($match) $replacementSection }, 1)
if ($configText -ne $originalConfig) {
    if ($originalConfig) {
        [IO.File]::WriteAllText((Join-Path $runtimeRoot ('logs\wslconfig-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.bak')), $originalConfig, $utf8)
    }
    [IO.File]::WriteAllText($wslConfigPath, $configText.TrimStart("`r", "`n"), $utf8)
}

$registrations = @(Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss\*' -ErrorAction SilentlyContinue)
$existing = $registrations | Where-Object { $_.DistributionName -eq $distroName }
if ($existing) {
    $registeredPath = $existing.BasePath
    if ($registeredPath.StartsWith('\\?\')) { $registeredPath = $registeredPath.Substring(4) }
    if ($registeredPath.TrimEnd('\') -ne $distroRoot.TrimEnd('\')) {
        throw "Existing $distroName is registered outside the expected G: directory: $($existing.BasePath)"
    }
    Write-Host "Already registered: $distroName at $distroRoot"
    exit 0
}

$running = Invoke-WslControl '--list --running --quiet'
if ($running.ExitCode -eq 0 -and $running.Output.Trim()) {
    throw 'Other WSL distributions are running. Close them before initial setup so the G: swap configuration takes effect.'
}

$archiveName = 'ubuntu-base-24.04.4-base-amd64.tar.gz'
$expectedHash = 'c1e67ef7b17a6300e136118bd1dc04725009cb376c1aad10abcf8cd453628d58'
$archivePath = Join-Path $runtimeRoot ('downloads\' + $archiveName)
$bases = @(
    'https://mirrors.ustc.edu.cn/ubuntu-cdimage/ubuntu-base/releases/24.04/release',
    'https://mirrors.tuna.tsinghua.edu.cn/ubuntu-cdimage/ubuntu-base/releases/24.04/release',
    'https://cdimage.ubuntu.com/ubuntu-base/releases/24.04/release'
)
$validArchive = (Test-Path -LiteralPath $archivePath) -and ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash -eq $expectedHash)
if (-not $validArchive) {
    foreach ($downloadBase in $bases) {
        Write-Host "Downloading Ubuntu Base from $downloadBase"
        & curl.exe --fail --location --retry 2 --connect-timeout 10 --max-time 600 --continue-at - --output ($archivePath + '.part') ($downloadBase + '/' + $archiveName)
        if ($LASTEXITCODE -eq 0) {
            if ((Get-FileHash -LiteralPath ($archivePath + '.part') -Algorithm SHA256).Hash -ne $expectedHash) {
                throw 'Ubuntu checksum mismatch. The partial file was retained for inspection; nothing was imported.'
            }
            Move-Item -LiteralPath ($archivePath + '.part') -Destination $archivePath -Force
            $validArchive = $true
            break
        }
    }
}
if (-not $validArchive) { throw 'Ubuntu download failed. Re-run this script on the faster network; partial downloads are retained on G:.' }
New-Item -ItemType Directory -Path $distroRoot -Force | Out-Null
$result = Invoke-WslControl ('--import ' + $distroName + ' "' + $distroRoot + '" "' + $archivePath + '" --version 2')
$result | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'logs\wsl-import.json') -Encoding UTF8
Write-Host $result.Output
if ($result.ExitCode -ne 0) {
    throw "WSL import failed: $($result.Error) $($result.Output). No Windows feature installation or restart was attempted."
}
Write-Host "Ubuntu registered at $distroRoot. Next: environment\research.ps1 -Action bootstrap"
