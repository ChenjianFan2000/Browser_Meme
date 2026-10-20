# Windows-side supervision remains in memory if the external G: volume disappears.
function ConvertTo-DownloadArgument {
    param([string]$Value)
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') { return $Value }
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Invoke-DownloadProcess {
    param(
        [string]$FilePath, [string[]]$NativeArguments,
        [scriptblock]$DriveProbe, [scriptblock]$Log,
        [int]$QuietSeconds = 300, [int]$MaximumSeconds = 0
    )
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo.FileName = $FilePath
    $process.StartInfo.Arguments = ($NativeArguments | ForEach-Object { ConvertTo-DownloadArgument $_ }) -join ' '
    $process.StartInfo.WorkingDirectory = $env:SystemRoot
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    $process.StartInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
    $process.StartInfo.StandardErrorEncoding = [Text.Encoding]::UTF8
    $started = [DateTime]::UtcNow
    $lastOutput = $started
    $lastProbe = $started.AddSeconds(-5)
    $lastNotice = $started
    $reason = 'exit'
    $code = 1
    $processStarted = $false
    try {
        if (-not $process.Start()) { throw 'Could not start the download process.' }
        $processStarted = $true
        $outTask = $process.StandardOutput.ReadLineAsync()
        $errTask = $process.StandardError.ReadLineAsync()
        while ($true) {
            foreach ($kind in @('out', 'err')) {
                $task = if ($kind -eq 'out') { $outTask } else { $errTask }
                while ($null -ne $task -and $task.IsCompleted) {
                    $line = $task.GetAwaiter().GetResult()
                    if ($null -eq $line) { $task = $null; break }
                    & $Log $line
                    $lastOutput = [DateTime]::UtcNow
                    $task = if ($kind -eq 'out') { $process.StandardOutput.ReadLineAsync() } else { $process.StandardError.ReadLineAsync() }
                }
                if ($kind -eq 'out') { $outTask = $task } else { $errTask = $task }
            }
            if ($process.HasExited -and $null -eq $outTask -and $null -eq $errTask) {
                $code = $process.ExitCode
                break
            }
            $now = [DateTime]::UtcNow
            if (($now - $lastProbe).TotalSeconds -ge 5) {
                if (-not (& $DriveProbe)) { $reason = 'storage-unavailable'; $code = 75; break }
                $lastProbe = $now
            }
            if (($now - $lastOutput).TotalSeconds -ge $QuietSeconds) {
                $reason = 'unresponsive'; $code = 124; break
            }
            if ($MaximumSeconds -gt 0 -and ($now - $started).TotalSeconds -ge $MaximumSeconds) {
                $reason = 'timeout'; $code = 124; break
            }
            if (($now - $lastNotice).TotalSeconds -ge 15) {
                & $Log ('[host] Monitoring WSL; {0:N0}s since its last output.' -f ($now-$lastOutput).TotalSeconds)
                $lastNotice = $now
            }
            Start-Sleep -Milliseconds 150
        }
    }
    finally {
        if ($processStarted -and -not $process.HasExited) {
            $process.Kill()
            [void]$process.WaitForExit(5000)
        }
        $process.Dispose()
    }
    return [pscustomobject]@{ Code = $code; Reason = $reason }
}

function Invoke-ResilientDownload {
    param([string]$ProjectRoot, [string]$DistroName, [string]$Profile, [string]$Mirror)
    $logRoot = Join-Path $ProjectRoot '.runtime\logs'
    $marker = Join-Path $ProjectRoot '.runtime\config\download-storage-id.txt'
    if (-not (Test-Path -LiteralPath $marker)) {
        [IO.File]::WriteAllText($marker, [Guid]::NewGuid().ToString())
    }
    $storageId = [IO.File]::ReadAllText($marker).Trim()
    $logPath = Join-Path $logRoot ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-download-recovery.log')
    $pending = New-Object 'System.Collections.Generic.List[string]'
    $log = {
        param([string]$Line)
        Write-Host $Line
        $pending.Add($Line)
        if ($pending.Count -gt 500) { $pending.RemoveAt(0) }
        try {
            [IO.File]::AppendAllText($logPath, (($pending -join [Environment]::NewLine) + [Environment]::NewLine), [Text.Encoding]::UTF8)
            $pending.Clear()
        } catch { } # Keep a bounded in-memory tail until the same G: volume returns.
    }.GetNewClosure()
    $probe = {
        try { return [IO.File]::ReadAllText($marker).Trim() -eq $storageId }
        catch { return $false }
    }.GetNewClosure()
    $mutex = New-Object Threading.Mutex($false, ('Local\BrowserMemeDownload-' + $storageId))
    $acquired = $false
    $wslExe = Join-Path $env:SystemRoot 'System32\wsl.exe'
    try {
        try { $acquired = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $acquired = $true }
        if (-not $acquired) { & $log 'Another supervised download is already running.'; return 73 }
        $linuxRoot = '/mnt/g/' + $ProjectRoot.Substring(3).Replace('\', '/')
        $boot = 'set -e; mountpoint -q /mnt/g || mount -t drvfs G: /mnt/g -o metadata,uid=1000,gid=1000,umask=022 || exit 75; touch /opt/browser-meme/tmp/.download-storage-check || exit 75; exec runuser -u research -- bash "$1" "$2" "$3" download'
        $native = @('--distribution', $DistroName, '--user', 'root', '--cd', '/', '--exec', 'bash', '-c', $boot,
                    '--', ($linuxRoot + '/environment/scripts/download.sh'), $Profile, $Mirror)
        $maximumAttempts = if ($env:BM_HOST_RETRIES) { [int]$env:BM_HOST_RETRIES } else { 6 }
        $driveWait = if ($env:BM_DRIVE_WAIT_SECONDS) { [int]$env:BM_DRIVE_WAIT_SECONDS } else { 600 }
        $quietLimit = if ($env:BM_HOST_QUIET_SECONDS) { [int]$env:BM_HOST_QUIET_SECONDS } else { 300 }
        & $log ('Live download log: ' + $logPath)
        $last = $null
        for ($attempt = 1; $attempt -le $maximumAttempts; $attempt++) {
            $deadline = [DateTime]::UtcNow.AddSeconds($driveWait)
            $stable = 0
            $notice = [DateTime]::MinValue
            while ($stable -lt 3 -and [DateTime]::UtcNow -lt $deadline) {
                if (& $probe) { $stable++ } else { $stable = 0 }
                if ($stable -eq 0 -and ([DateTime]::UtcNow-$notice).TotalSeconds -ge 15) {
                    & $log '[host] Waiting for the original G: volume; cached downloads are retained.'
                    $notice = [DateTime]::UtcNow
                }
                if ($stable -lt 3) { Start-Sleep -Seconds 2 }
            }
            if ($stable -lt 3) { & $log '[host] Drive wait limit reached. Reconnect G: and rerun Download-All.cmd.'; return 75 }
            if ($null -ne $last -and $last.Reason -ne 'exit') {
                & $log ('[host] Restarting only the research distribution after ' + $last.Reason)
                $reset = Invoke-DownloadProcess -FilePath $wslExe -NativeArguments @('--terminate', $DistroName) `
                    -DriveProbe $probe -Log $log -QuietSeconds 30 -MaximumSeconds 30
                if ($reset.Code -ne 0) { & $log '[host] WSL recovery failed; stop here and inspect its service. No data has been reset.'; return $reset.Code }
            }
            & $log ("[host] Download session $attempt/$maximumAttempts; verified files will be reused.")
            $last = Invoke-DownloadProcess -FilePath $wslExe -NativeArguments $native -DriveProbe $probe -Log $log -QuietSeconds $quietLimit
            if ($last.Code -eq 0) { & $log '[host] All requested downloads completed.'; return 0 }
            if ($last.Code -in @(73, 130)) { return $last.Code }
            # An EIO/read-only filesystem can remain after G: has reappeared.
            if ($last.Code -eq 75) { $last.Reason = 'storage-error' }
            & $log ("[host] Session stopped: exit $($last.Code), $($last.Reason). Partial files retained.")
            if ($attempt -lt $maximumAttempts) { Start-Sleep -Seconds ([Math]::Min(15 * $attempt, 60)) }
        }
        & $log '[host] Recovery attempt limit reached. See the live log; rerun later to resume.'
        return $last.Code
    }
    finally {
        if ($acquired) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
