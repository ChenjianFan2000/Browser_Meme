[CmdletBinding()]
param(
    [ValidateSet('bootstrap', 'prepare', 'download', 'install', 'doctor', 'verify-base', 'shell', 'gitlab-start', 'gitlab-stop', 'webchore-start', 'webchore-stop')]
    [string]$Action = 'doctor',
    [ValidateSet('core', 'agentlab', 'webchore', 'images', 'runtimes', 'all')]
    [string]$Profile = 'core',
    [ValidateSet('cn', 'official')]
    [string]$Mirror = 'cn'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetPathRoot($projectRoot) -ne 'G:\') { throw 'Run this project from G:.' }
$env:TEMP = Join-Path $projectRoot '.runtime\temp'
$env:TMP = $env:TEMP
$env:WSL_UTF8 = '1'
New-Item -ItemType Directory -Path $env:TEMP -Force | Out-Null
$linuxRoot = '/mnt/g/' + $projectRoot.Substring(3).Replace('\', '/')
$distroName = 'BrowserMeme-Ubuntu'
$registration = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss\*' -ErrorAction SilentlyContinue | Where-Object { $_.DistributionName -eq $distroName }
if (-not $registration) { throw 'Run environment\Setup-Wsl.ps1 first.' }
$registeredPath = $registration.BasePath
if ($registeredPath.StartsWith('\\?\')) { $registeredPath = $registeredPath.Substring(4) }
if ($registeredPath.TrimEnd('\') -ne (Join-Path $projectRoot '.runtime\wsl\Ubuntu-24.04').TrimEnd('\')) {
    throw 'The research distro is not in the expected G: directory; stopped before running setup.'
}
if ($Action -eq 'download') {
    . (Join-Path $PSScriptRoot 'Download-Recovery.ps1')
    exit (Invoke-ResilientDownload -ProjectRoot $projectRoot -DistroName $distroName -Profile $Profile -Mirror $Mirror)
}
# Mount G: after Linux has booted, avoiding a systemd/DrvFs startup dependency.
# Keep C: unmounted; all commands and caches use G:-backed storage.
& wsl.exe --distribution $distroName --user root --cd / --exec bash -c 'mountpoint -q /mnt/g || mount -t drvfs G: /mnt/g -o metadata,uid=1000,gid=1000,umask=022'
if ($LASTEXITCODE -ne 0) { throw 'Unable to mount the G: project drive inside WSL.' }
if ($Action -eq 'shell') {
    & wsl.exe --distribution $distroName --user research --cd $linuxRoot
    exit $LASTEXITCODE
}
$scripts = @{
    bootstrap = 'bootstrap.sh'
    prepare = 'prepare.sh'
    download = 'download.sh'
    install = 'install.sh'
    doctor = 'doctor.sh'
    'verify-base' = 'verify-base.sh'
    'gitlab-start' = 'sites.sh'
    'gitlab-stop' = 'sites.sh'
    'webchore-start' = 'sites.sh'
    'webchore-stop' = 'sites.sh'
}
$linuxUser = if ($Action -eq 'bootstrap') { 'root' } else { 'research' }
$logDirectory = Join-Path $projectRoot '.runtime\logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $Action + '.log')
$ErrorActionPreference = 'Continue'
& wsl.exe --distribution $distroName --user $linuxUser --exec bash ($linuxRoot + '/environment/scripts/' + $scripts[$Action]) $Profile $Mirror $Action 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $logPath
$actionExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($actionExitCode -ne 0) { throw "$Action failed (exit $actionExitCode). Log: $logPath" }
if ($Action -in @('gitlab-start', 'webchore-start')) {
    # systemd services alone do not keep a WSL distro alive after its client exits.
    $keeperArgs = @('--distribution', $distroName, '--user', 'research', '--cd', '/', '--exec', 'bash', ($linuxRoot + '/environment/scripts/site-keepalive.sh'))
    $keeper = Start-Process -FilePath "$env:SystemRoot\System32\wsl.exe" -ArgumentList $keeperArgs -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput ($logPath + '.keeper.out') -RedirectStandardError ($logPath + '.keeper.err')
    Write-Host "Site runtime keeper started (PID $($keeper.Id)); it exits after both site groups stop."
}
if ($Action -eq 'bootstrap') {
    # Only restart this dedicated research distro, never another user's distro.
    & wsl.exe --terminate $distroName
    if ($LASTEXITCODE -ne 0) { throw 'Unable to restart the research distribution.' }
    & wsl.exe --distribution $distroName --user root --exec systemctl enable --now docker
    if ($LASTEXITCODE -ne 0) { throw 'Docker service did not start. Review the bootstrap log.' }
    & wsl.exe --distribution $distroName --user research --exec docker info --format '{{.ServerVersion}} {{.DockerRootDir}}'
    if ($LASTEXITCODE -ne 0) { throw 'The research user cannot access Docker.' }
}
