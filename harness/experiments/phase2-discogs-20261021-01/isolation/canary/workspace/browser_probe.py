import json, threading
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
