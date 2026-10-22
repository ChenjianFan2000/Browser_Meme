"""Run via WSL python3 stdin; contains only generic infrastructure canaries."""
import json
import os
import socket
import sys
import pathlib
import subprocess
import threading
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import urllib.request

ROOT = pathlib.Path('/opt/browser-meme/tmp/phase2-isolation-audit')
EXE = ROOT / 'package/vendor/x86_64-unknown-linux-musl/bin/codex'
WORK = ROOT / 'workspace'
WORK.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))
from unix_gateway import make_gateway
(ROOT / 'blocked-canary.txt').write_text('generic-blocked')
(WORK / 'allowed-canary.txt').write_text('generic-allowed')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'<title>Generic network canary</title><button onclick="this.textContent=String.fromCharCode(67,108,105,99,107,101,100)">Canary</button>')

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
denied_server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=denied_server.serve_forever, daemon=True).start()


class PortFilter(BaseHTTPRequestHandler):
    def do_GET(self):
        target = urlsplit(self.path)
        if target.scheme != 'http' or target.hostname != '127.0.0.1' or target.port != server.server_port:
            self.send_error(403, 'Destination denied')
            return
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(self.path, timeout=3) as response:
            self.send_response(response.status)
            self.end_headers()
            self.wfile.write(response.read())

    def do_CONNECT(self):
        self.send_error(403, 'CONNECT denied for generic probe')

    def log_message(self, *args):
        pass


socket_path = ROOT / 'gateway.sock'
socket_path.unlink(missing_ok=True)
proxy = make_gateway(socket_path, f'http://127.0.0.1:{server.server_port}', '127.0.0.1', server.server_port)
threading.Thread(target=proxy.serve_forever, daemon=True).start()
forbidden_path = ROOT / 'forbidden.sock'
forbidden_path.unlink(missing_ok=True)
forbidden = socket.socket(socket.AF_UNIX)
forbidden.bind(str(forbidden_path)); forbidden.listen()
abstract = socket.socket(socket.AF_UNIX)
abstract.bind('\0phase2-isolation-host-canary'); abstract.listen()
probe = '''import json, os, pathlib, socket, urllib.request
out={}
os.environ['no_proxy']=''; os.environ['NO_PROXY']=''
import socketserver, threading, select
class Bridge(socketserver.BaseRequestHandler):
 def handle(self):
  upstream=socket.socket(socket.AF_UNIX); upstream.connect('SOCKETPATH')
  try:
   while True:
    ready,_,_=select.select([self.request,upstream],[],[],3)
    if not ready: break
    for source in ready:
     data=source.recv(65536)
     if not data: return
     (upstream if source is self.request else self.request).sendall(data)
  finally: upstream.close()
bridge=socketserver.ThreadingTCPServer(('127.0.0.1',0),Bridge)
threading.Thread(target=bridge.serve_forever,daemon=True).start()
os.environ['http_proxy']='http://127.0.0.1:'+str(bridge.server_address[1]); os.environ['HTTP_PROXY']=os.environ['http_proxy']
out['gateway_rejections']={}
for name,request in [('CONNECT','CONNECT 127.0.0.1:PORT HTTP/1.1\\r\\nHost: 127.0.0.1:PORT\\r\\n\\r\\n'),('wrong_host','GET http://127.0.0.1:PORT/ HTTP/1.1\\r\\nHost: attacker.invalid\\r\\n\\r\\n'),('url_credentials','GET http://user@127.0.0.1:PORT/ HTTP/1.1\\r\\nHost: 127.0.0.1:PORT\\r\\n\\r\\n'),('IPv6','GET http://[::1]:PORT/ HTTP/1.1\\r\\nHost: [::1]:PORT\\r\\n\\r\\n'),('chunked','POST http://127.0.0.1:PORT/ HTTP/1.1\\r\\nHost: 127.0.0.1:PORT\\r\\nTransfer-Encoding: chunked\\r\\n\\r\\n0\\r\\n\\r\\n')]:
 with socket.create_connection(bridge.server_address,timeout=3) as client:
  client.sendall(request.encode()); out['gateway_rejections'][name]=client.recv(256).split(b'\\r\\n')[0].decode()
for name,path in [('allowed','WORK/allowed-canary.txt'),('blocked','ROOT/blocked-canary.txt'),('docker_socket','/var/run/docker.sock')]:
 try: pathlib.Path(path).read_bytes(); out[name]='READ'
 except Exception as e: out[name]=type(e).__name__
for name,addr in [('host_loopback',('127.0.0.1',PORT)),('external_tcp',('1.1.1.1',443))]:
 try: socket.create_connection(addr,timeout=2).close(); out[name]='CONNECTED'
 except Exception as e: out[name]=type(e).__name__
for name,addr in [('forbidden_socket','FORBIDDENPATH'),('host_abstract_socket',chr(0)+'phase2-isolation-host-canary'),('docker_socket_connect','/var/run/docker.sock')]:
 try:
  sock=socket.socket(socket.AF_UNIX); sock.settimeout(1); sock.connect(addr); sock.close(); out[name]='CONNECTED'
 except Exception as e: out[name]=type(e).__name__
out['host_runtime_paths_visible']={path:pathlib.Path(path).exists() for path in ['/run/user/1000','/run/dbus/system_bus_socket','/tmp/.X11-unix','/mnt/g','/opt/browser-meme/secrets']}
try: out['proxy_http']=urllib.request.urlopen('http://127.0.0.1:PORT',timeout=3).read().decode()
except Exception as e: out['proxy_http']=repr(e)
try: out['proxy_wrong_port']=urllib.request.urlopen('http://127.0.0.1:DENIEDPORT',timeout=3).read().decode()
except Exception as e: out['proxy_wrong_port']=repr(e)
print(json.dumps(out))
from playwright.sync_api import sync_playwright
from unix_bridge import playwright_proxy
os.environ['TMPDIR']='WORK'; os.environ['HOME']='WORK'
browser_proxy_context=playwright_proxy('SOCKETPATH'); browser_proxy=browser_proxy_context.__enter__()
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/opt/browser-meme/browsers/chromium-1117/chrome-linux/chrome',headless=True,chromium_sandbox=True,timeout=10000,proxy=browser_proxy)
 page=browser.new_page(); page.goto('http://127.0.0.1:PORT',timeout=10000); page.get_by_role('button',name='Canary').click(); assert page.get_by_role('button',name='Clicked').is_visible(); page.screenshot(path='WORK/generic-browser.png')
 print(json.dumps({'browser_positive':True,'chromium_sandbox':True,'title':page.title()})); browser.close()
browser_proxy_context.__exit__(None,None,None)
'''.replace('WORK', str(WORK)).replace('ROOT', str(ROOT)).replace('SOCKETPATH', str(socket_path)).replace('FORBIDDENPATH', str(forbidden_path)).replace('DENIEDPORT', str(denied_server.server_port)).replace('PORT', str(server.server_port))
(WORK / 'network_probe.py').write_text(probe)
fs = {':root': 'deny', ':minimal': 'read', ':workspace_roots': 'write', str(EXE): 'read', str(socket_path): 'read'}
fs['/opt/browser-meme/envs/core']='read'
fs['/opt/browser-meme/browsers/chromium-1117']='read'
args = [str(EXE), 'sandbox', '-P', 'p2', '-C', str(WORK), '-c', 'permissions.p2.filesystem=' + json.dumps(fs).replace(': ', '='), '-c', 'permissions.p2.network.enabled=true', '-c', 'features.network_proxy=true', '-c', 'permissions.p2.network.allow_local_binding=true', '-c', 'permissions.p2.network.domains={"127.0.0.1"="allow"}', '/usr/bin/python3', str(WORK / 'network_probe.py')]
args[args.index('permissions.p2.network.domains={"127.0.0.1"="allow"}')] = 'permissions.p2.network.domains={}'
args[args.index('/usr/bin/python3'):args.index('/usr/bin/python3')] = ['-c', 'permissions.p2.network.dangerously_allow_all_unix_sockets=true']
args[args.index('/usr/bin/python3'):args.index('/usr/bin/python3')] = ['-c', 'permissions.p2.network.unix_sockets={"'+str(socket_path)+'"="allow"}']
env = os.environ.copy()
args[args.index('/usr/bin/python3')]='/opt/browser-meme/envs/core/bin/python'
result = subprocess.run(args, capture_output=True, text=True, timeout=20, env=env)
print(json.dumps(dict(command=args, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)))
server.shutdown()
denied_server.shutdown()
proxy.shutdown()
forbidden.close(); abstract.close()
forbidden_path.unlink(missing_ok=True); socket_path.unlink(missing_ok=True)
