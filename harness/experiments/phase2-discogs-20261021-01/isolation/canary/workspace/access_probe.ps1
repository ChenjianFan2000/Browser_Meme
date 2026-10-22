$ErrorActionPreference='Stop'
$results=@{}
function CheckRead($name,$path) {try {[void][IO.File]::ReadAllText($path);$results[$name]='READ'}catch {$results[$name]=$_.Exception.GetType().FullName}}
CheckRead 'allowed' 'G:/Browser_Meme/harness/experiments/phase2-discogs-20261021-01/isolation/canary/workspace/allowed.txt'
CheckRead 'blocked_absolute' 'G:/Browser_Meme/harness/experiments/phase2-discogs-20261021-01/isolation/canary/blocked.txt'
CheckRead 'blocked_case' 'g:/browser_meme/harness/experiments/phase2-discogs-20261021-01/isolation/canary/blocked.txt'
CheckRead 'blocked_parent' 'G:/Browser_Meme/harness/experiments/phase2-discogs-20261021-01/isolation/canary/workspace/../blocked.txt'
CheckRead 'repo_agents' 'G:/Browser_Meme/AGENTS.md'
try {[void](Get-Process -Id 26236);$results['host_process']='VISIBLE'}catch {$results['host_process']='DENIED_OR_ABSENT'}
try {$c=New-Object Net.Sockets.TcpClient;$t=$c.ConnectAsync('127.0.0.1',14188);if($t.Wait(2000)){$results['host_loopback']='CONNECTED'}else{$results['host_loopback']='TIMEOUT'};$c.Dispose()}catch {$results['host_loopback']='DENIED'}
try {$c=New-Object Net.Sockets.TcpClient;$t=$c.ConnectAsync('1.1.1.1',443);if($t.Wait(2000)){$results['external_tcp']='CONNECTED'}else{$results['external_tcp']='TIMEOUT'};$c.Dispose()}catch {$results['external_tcp']='DENIED'}
$results|ConvertTo-Json -Compress
