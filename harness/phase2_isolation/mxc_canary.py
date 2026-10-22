"""Generic, no-model MXC access probe. Does not read target website material."""
import json
import pathlib
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / 'harness/experiments/phase2-discogs-20261021-01/isolation'
WORK = OUT / 'canary/workspace'
CODEX = pathlib.Path('C:/Users/29935/AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'<html><title>Generic isolation canary</title><button>Canary</button></html>')

    def log_message(self, *args):
        pass


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / 'allowed.txt').write_text('generic-canary-allowed', encoding='utf-8')
    (WORK.parent / 'blocked.txt').write_text('generic-canary-blocked', encoding='utf-8')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host_canary = subprocess.Popen(['powershell.exe', '-NoProfile', '-Command', 'Start-Sleep -Seconds 120'], creationflags=0x08000000)
    path = str(WORK).replace('\\', '/')
    blocked = str(WORK.parent / 'blocked.txt').replace('\\', '/')
    probe = '''$ErrorActionPreference='Stop'
$results=@{}
function CheckRead($name,$path) {try {[void][IO.File]::ReadAllText($path);$results[$name]='READ'}catch {$results[$name]=$_.Exception.GetType().FullName}}
CheckRead 'allowed' 'WORK/allowed.txt'
CheckRead 'blocked_absolute' 'BLOCKED'
CheckRead 'blocked_case' 'LOWER'
CheckRead 'blocked_parent' 'WORK/../blocked.txt'
CheckRead 'repo_agents' 'G:/Browser_Meme/AGENTS.md'
try {[void](Get-Process -Id HOSTPID);$results['host_process']='VISIBLE'}catch {$results['host_process']='DENIED_OR_ABSENT'}
try {$c=New-Object Net.Sockets.TcpClient;$t=$c.ConnectAsync('127.0.0.1',PORT);if($t.Wait(2000)){$results['host_loopback']='CONNECTED'}else{$results['host_loopback']='TIMEOUT'};$c.Dispose()}catch {$results['host_loopback']='DENIED'}
try {$c=New-Object Net.Sockets.TcpClient;$t=$c.ConnectAsync('1.1.1.1',443);if($t.Wait(2000)){$results['external_tcp']='CONNECTED'}else{$results['external_tcp']='TIMEOUT'};$c.Dispose()}catch {$results['external_tcp']='DENIED'}
$results|ConvertTo-Json -Compress
'''.replace('WORK', path).replace('BLOCKED', blocked).replace('LOWER', blocked.lower()).replace('HOSTPID', str(host_canary.pid)).replace('PORT', str(server.server_port))
    (WORK / 'access_probe.ps1').write_text(probe, encoding='utf-8')
    browser_probe = '''import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200); self.end_headers(); self.wfile.write(b'<title>Generic canary</title><button onclick="this.textContent=String.fromCharCode(67,108,105,99,107,101,100)">Canary</button>')
 def log_message(self,*args): pass
server=HTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='C:/Users/29935/AppData/Local/Google/Chrome/Application/chrome.exe',headless=True,chromium_sandbox=True)
 page=browser.new_page(); page.goto('http://127.0.0.1:'+str(server.server_port)); page.get_by_role('button',name='Canary').click(); assert page.get_by_role('button',name='Clicked').is_visible()
 print(json.dumps({'title':page.title(),'clicked':True,'chromium_sandbox':True})); browser.close()
server.shutdown()
'''
    (WORK / 'browser_probe.py').write_text(browser_probe, encoding='utf-8')
    args = [str(CODEX), 'sandbox', '-P', 'phase2-canary', '-C', str(WORK)]
    configs = {
        'windows.sandbox': 'mxc',
        'permissions.phase2-canary.filesystem.:root': 'deny',
        'permissions.phase2-canary.filesystem.:minimal': 'read',
        'permissions.phase2-canary.filesystem.:workspace_roots': 'write',
        'permissions.phase2-canary.network.enabled': 'false',
    }
    for key, value in configs.items():
        args += ['-c', f'{key}={value}']
    args += ['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(WORK / 'access_probe.ps1')]
    try:
        for name, additions in [('offline', []), ('managed-network', ['-c', 'permissions.phase2-canary.network.enabled=true', '-c', 'features.network_proxy=true', '-c', 'permissions.phase2-canary.network.allow_local_binding=true', '-c', 'permissions.phase2-canary.network.domains={"example.com"="allow"}'])]:
            command = args[:args.index('powershell.exe')] + additions + args[args.index('powershell.exe'):]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            evidence = dict(command=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
            (OUT / f'mxc-access-probe-{name}.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(evidence, ensure_ascii=False))
        venv = ROOT / '.runtime/phase1-discogs-pw-20261020-1633/venv'
        base = args[:args.index('powershell.exe')]
        paths = {':root': 'deny', ':minimal': 'read', ':workspace_roots': 'write'}
        for folder in [str(venv), 'D:/Anaconda/Lib', 'D:/Anaconda/DLLs', 'D:/Anaconda/python.exe', 'D:/Anaconda/python311.dll', 'D:/Anaconda/python3.dll', 'C:/Users/29935/AppData/Local/Google/Chrome/Application']:
            paths[folder.replace('\\', '/')] = 'read'
        for dll in pathlib.Path('D:/Anaconda').glob('*.dll'):
            paths[dll.as_posix()] = 'read'
        table = '{' + ','.join(json.dumps(k) + '=' + json.dumps(v) for k, v in paths.items()) + '}'
        base += ['-c', 'permissions.phase2-canary.filesystem=' + table]
        base += [str(venv / 'Scripts/python.exe'), str(WORK / 'browser_probe.py')]
        stdout_path = OUT / 'mxc-browser.stdout.txt'
        stderr_path = OUT / 'mxc-browser.stderr.txt'
        with stdout_path.open('w', encoding='utf-8') as stdout, stderr_path.open('w', encoding='utf-8') as stderr:
            child = subprocess.Popen(base, stdout=stdout, stderr=stderr)
            try:
                exit_code = child.wait(timeout=30)
                timed_out = False
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill.exe', '/PID', str(child.pid), '/T', '/F'], capture_output=True)
                child.wait(timeout=10)
                exit_code = child.returncode
                timed_out = True
        evidence = dict(command=base, exit_code=exit_code, timeout=timed_out, stdout=stdout_path.read_text(encoding='utf-8'), stderr=stderr_path.read_text(encoding='utf-8'))
        (OUT / 'mxc-browser-probe.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False))
    finally:
        host_canary.terminate()
        host_canary.wait()
        server.shutdown()


if __name__ == '__main__':
    main()
