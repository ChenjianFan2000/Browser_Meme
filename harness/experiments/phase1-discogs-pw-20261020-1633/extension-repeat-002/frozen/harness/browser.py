"""Site-independent Chrome DevTools adapter.

Uses an isolated browser context for each case. Model artifacts can specify
locators and ordinary UI actions, never arbitrary JavaScript or HTTP mutations.
The installed agent-browser was probed first but its daemon timed out; this
adapter provides the same confirm/scroll/action/wait/readback protocol via CDP.
"""
from __future__ import annotations

import base64
import fnmatch
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.request
from urllib.parse import urljoin, urlparse


# This code is infrastructure-owned, not model-supplied. :has-text is the one
# supported extension to native CSS; no input is interpolated as executable JS.
SELECT = r"""
function query(selector) {
  const texts = [];
  const css = selector.replace(/:has-text\((['"])(.*?)\1\)/g, (_,q,t) => {
    texts.push(t); return '';
  });
  return Array.from(document.querySelectorAll(css || '*')).filter(
    e => texts.every(t => (e.innerText || e.textContent || '').includes(t)));
}
function visible(e) {
  const r=e.getBoundingClientRect(), s=getComputedStyle(e);
  return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none';
}
"""


class Browser:
    """One case, one incognito context, with a bounded CDP connection."""

    def __init__(self, site: dict, session: str, timeout: float = 30,
                 cdp_url: str | None = None, event_sink=None):
        self.site = site
        self.session = session
        self.timeout = timeout
        self.cdp_url = cdp_url
        self.event_sink = event_sink or (lambda event: None)
        self.ws = None
        self.context_id = None
        self.session_id = None
        self.counter = 0
        self.child = None
        self.owns_browser = False
        self.network_pending = set()
        self.last_network_change = time.monotonic()

    def emit(self, stage: str, **data):
        self.event_sink({"stage": stage, "time": time.time(), **data})

    def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        return (url == "about:blank" or parsed.scheme == "data" or
                (parsed.scheme in ("http", "https", "ws", "wss") and
                 parsed.hostname in self.site.get("allowed_hosts", ["127.0.0.1", "localhost"])
                 and parsed.hostname in ("127.0.0.1", "localhost", "::1")))

    @staticmethod
    def _local_json(url: str):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=3) as response:
            return json.load(response)

    def _launch(self):
        candidates = [
            os.environ.get("HARNESS_CHROME"),
            shutil.which("google-chrome"), shutil.which("chromium"),
            shutil.which("chrome"),
        ]
        if os.name == "nt":
            for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles"),
                         os.environ.get("ProgramFiles(x86)"),
                         r"C:\Users\29935\AppData\Local"):
                if base:
                    candidates.append(str(Path(base) / "Google/Chrome/Application/chrome.exe"))
        executable = next((p for p in candidates if p and Path(p).is_file()), None)
        if not executable:
            raise RuntimeError("infrastructure: Chrome not found; set HARNESS_CHROME or use --cdp")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        directory = Path(__file__).resolve().parents[1] / ".runtime/browser-profiles" / self.session
        directory.mkdir(parents=True, exist_ok=False)
        log = (directory / "chrome.log").open("ab")
        self.child = subprocess.Popen(
            [executable, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
             "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}",
             f"--user-data-dir={directory / 'profile'}", "about:blank"],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        log.close()
        self.cdp_url = f"http://127.0.0.1:{port}"
        self.owns_browser = True
        self.emit("browser_launch", port=port, pid=self.child.pid, profile=str(directory))

    def start(self):
        try:
            import websocket
        except ImportError as exc:
            raise RuntimeError("infrastructure: install websocket-client for the browser adapter") from exc
        if self.cdp_url is None:
            self._launch()
        if urlparse(self.cdp_url).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError("infrastructure: CDP must be an explicitly local experiment browser")
        deadline = time.monotonic() + self.timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                version = self._local_json(self.cdp_url.rstrip("/") + "/json/version")
                self.ws = websocket.create_connection(
                    version["webSocketDebuggerUrl"], timeout=self.timeout,
                    suppress_origin=True, http_no_proxy=["127.0.0.1", "localhost", "::1"])
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.2)
        if not self.ws:
            raise RuntimeError(f"infrastructure: Chrome endpoint unavailable: {last_error}")
        self.context_id = self.call("Target.createBrowserContext", {}, browser=True)["browserContextId"]
        target = self.call("Target.createTarget", {
            "url": "about:blank", "browserContextId": self.context_id}, browser=True)["targetId"]
        self.session_id = self.call("Target.attachToTarget", {
            "targetId": target, "flatten": True}, browser=True)["sessionId"]
        for method in ("Page.enable", "Runtime.enable", "Network.enable"):
            self.call(method)
        self.call("Emulation.setDeviceMetricsOverride", {
            "width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
        self.call("Network.setCacheDisabled", {"cacheDisabled": True})
        # Block external requests before navigating the model's target.
        self.call("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})
        self.emit("browser_ready", browser=version.get("Browser"),
                  context=self.context_id, transport="cdp", fresh_context=True)

    def _send(self, method, params, browser=False):
        self.counter += 1
        message = {"id": self.counter, "method": method, "params": params}
        if not browser and self.session_id:
            message["sessionId"] = self.session_id
        self.ws.send(json.dumps(message))
        return self.counter

    def call(self, method, params=None, browser=False):
        request_id = self._send(method, params or {}, browser)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            self.ws.settimeout(max(0.05, deadline - time.monotonic()))
            try:
                message = json.loads(self.ws.recv())
            except Exception as exc:
                raise RuntimeError(f"infrastructure: CDP {method}: {exc}") from exc
            event = message.get("method")
            data = message.get("params", {})
            if event == "Fetch.requestPaused":
                allowed = self._allowed(data["request"]["url"])
                self._send("Fetch.continueRequest" if allowed else "Fetch.failRequest",
                           {"requestId": data["requestId"]} if allowed else
                           {"requestId": data["requestId"], "errorReason": "BlockedByClient"})
                if not allowed:
                    self.emit("external_request_blocked", url=data["request"]["url"])
            elif event == "Network.requestWillBeSent":
                if data.get("type") not in ("WebSocket", "EventSource"):
                    self.network_pending.add(data["requestId"])
                    self.last_network_change = time.monotonic()
            elif event in ("Network.loadingFinished", "Network.loadingFailed"):
                self.network_pending.discard(data["requestId"])
                self.last_network_change = time.monotonic()
            elif event == "Network.responseReceived":
                response = data.get("response", {})
                self.emit("network_response", url=response.get("url"),
                          status=response.get("status"), mime_type=response.get("mimeType"))
            elif event == "Page.javascriptDialogOpening":
                self.emit("dialog", type=data.get("type"), message=data.get("message"))
                self._send("Page.handleJavaScriptDialog", {"accept": False})
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"infrastructure: CDP {method}: {message['error']}")
                return message.get("result", {})
        raise RuntimeError(f"timing: CDP {method} exceeded {self.timeout}s")

    def evaluate(self, body: str, args=None):
        expression = "(function(args){" + SELECT + body + "})(" + json.dumps(args) + ")"
        result = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True})
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise RuntimeError("implementation: DOM observation failed: " +
                               details.get("exception", {}).get("description", str(details)))
        return result.get("result", {}).get("value")

    def _target(self, selector: str):
        result = self.evaluate("""
const all=query(args); if(all.length!==1) return {count:all.length};
const e=all[0]; e.scrollIntoView({block:'center',inline:'center',behavior:'instant'});
const r=e.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2;
const hit=document.elementFromPoint(x,y);
return {count:1,visible:visible(e),disabled:!!e.disabled,
 x,y,covered:!!hit && hit!==e && !e.contains(hit),checked:!!e.checked,
 tag:e.tagName, text:(e.innerText || e.getAttribute('aria-label') || '').slice(0,300)};
""", selector)
        self.emit("confirm_target", selector=selector, result=result)
        if result.get("count") != 1:
            raise RuntimeError(f"locator: expected exactly one target for {selector!r}, got {result.get('count')}")
        self.emit("scroll_into_view", selector=selector, x=result["x"], y=result["y"])
        if not result["visible"] or result["disabled"] or result["covered"]:
            raise RuntimeError(f"locator: target unavailable for interaction: {result}")
        return result

    def _click(self, target):
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            payload = {"type": kind, "x": target["x"], "y": target["y"]}
            if kind != "mouseMoved":
                payload.update(button="left", clickCount=1)
            self.call("Input.dispatchMouseEvent", payload)

    def _key(self, key: str):
        names = {"Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, "Delete": 46,
                 "ArrowDown": 40, "ArrowUp": 38, "ArrowLeft": 37, "ArrowRight": 39,
                 "Home": 36, "End": 35, "Space": 32}
        pieces = key.split("+")
        actual = pieces[-1]
        modifiers = (2 if "Control" in pieces else 0) | (8 if "Shift" in pieces else 0)
        modifiers |= (1 if "Alt" in pieces else 0) | (4 if "Meta" in pieces else 0)
        code = names.get(actual, ord(actual.upper()) if len(actual) == 1 else 0)
        for kind in ("keyDown", "keyUp"):
            params = {"type": kind, "key": actual, "windowsVirtualKeyCode": code,
                      "nativeVirtualKeyCode": code, "modifiers": modifiers}
            if kind == "keyDown" and actual == "Enter":
                params["text"] = "\r"
            self.call("Input.dispatchKeyEvent", params)

    def act(self, action: dict):
        kind = action["kind"]
        self.emit("action_start", action=action)
        if kind == "open":
            url = urljoin(self.site["base_url"], action["url"])
            if not self._allowed(url):
                raise RuntimeError(f"infrastructure: disallowed navigation: {url}")
            self.emit("confirm_target", url=url, target_type="navigation")
            self.emit("scroll_into_view", applicable=False, reason="navigation has no DOM target")
            result = self.call("Page.navigate", {"url": url})
            if result.get("errorText"):
                raise RuntimeError(f"infrastructure: navigation failed: {result['errorText']}")
        elif kind in ("back", "reload"):
            if kind == "reload":
                self.call("Page.reload")
            else:
                history = self.call("Page.getNavigationHistory")
                index = history["currentIndex"] - 1
                if index < 0:
                    raise RuntimeError("implementation: no back history")
                self.call("Page.navigateToHistoryEntry", {"entryId": history["entries"][index]["id"]})
        else:
            target = self._target(action["selector"]) if action.get("selector") else None
            if kind == "click":
                self._click(target)
            elif kind == "hover":
                self.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": target["x"], "y": target["y"]})
            elif kind in ("fill", "focus", "press", "select"):
                if target:
                    self._click(target)
                if kind == "fill":
                    self._key("Control+a")
                    self._key("Backspace")
                    if str(action["value"]):
                        self.call("Input.insertText", {"text": str(action["value"])})
                elif kind == "press":
                    self._key(action["key"])
                elif kind == "select":
                    index = self.evaluate("""
const e=query(args.selector)[0];
return Array.from(e.options).findIndex(o=>o.value===String(args.value));
""", action)
                    if index < 0:
                        raise RuntimeError("locator: requested option does not exist")
                    self._key("Home")
                    for _ in range(index):
                        self._key("ArrowDown")
                    self._key("Enter")
            elif kind in ("check", "uncheck"):
                if target["checked"] != (kind == "check"):
                    self._click(target)
            else:
                raise RuntimeError(f"implementation: unsupported action {kind}")
        self.emit("action_complete", kind=kind)

    def wait(self, spec: dict):
        self.emit("wait_start", condition=spec)
        deadline = time.monotonic() + self.timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                state = self.evaluate("""
return {url:location.href, ready:document.readyState, text:document.body?.innerText || '',
 matched:args.kind==='selector' ? query(args.value).some(visible) : false};
""", spec)
                kind, value = spec["kind"], spec["value"]
                passed = ((kind == "selector" and state["matched"]) or
                          (kind == "text" and value in state["text"]) or
                          (kind == "url" and fnmatch.fnmatch(state["url"], value)) or
                          (kind == "load" and state["ready"] in (
                              ("interactive", "complete") if value == "domcontentloaded" else ("complete",))))
                if kind == "load" and value == "networkidle":
                    passed = passed and not self.network_pending and time.monotonic() - self.last_network_change >= 0.5
                if passed:
                    self.emit("wait_complete", condition=spec)
                    return
            except RuntimeError as exc:
                last_error = str(exc)
            time.sleep(0.1)
        raise RuntimeError(f"timing: wait not satisfied: {spec}; {last_error or ''}")

    def observe(self, readouts: dict) -> dict:
        observation = self.evaluate("""
const result={url:location.href,title:document.title,text:document.body?.innerText || '',fields:{},errors:{}};
for(const [key,spec] of Object.entries(args)){
 try {
  const nodes=query(spec.selector), e=nodes[0];
  if(spec.kind==='count'){result.fields[key]=nodes.length;continue;}
  if(spec.kind==='visible'){result.fields[key]=nodes.some(visible);continue;}
  if(nodes.length!==1) throw Error('expected one element, got '+nodes.length);
  if(spec.kind==='text') result.fields[key]=e.innerText ?? e.textContent;
  else if(spec.kind==='value') result.fields[key]=e.value ?? null;
  else if(spec.kind==='checked') result.fields[key]=!!e.checked;
  else if(spec.kind==='attr') result.fields[key]=e.getAttribute(spec.attribute);
  else throw Error('unsupported readout '+spec.kind);
 }catch(err){result.fields[key]=null;result.errors[key]=String(err);}
}
return result;
""", readouts)
        if not self._allowed(observation["url"]):
            raise RuntimeError("infrastructure: observed disallowed page navigation")
        self.emit("readback", url=observation["url"], readout_errors=observation["errors"])
        return observation

    def screenshot(self, path: Path):
        data = self.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(base64.b64decode(data["data"]))

    def close(self):
        if self.ws:
            try:
                if self.context_id:
                    self.call("Target.disposeBrowserContext", {"browserContextId": self.context_id}, browser=True)
                if self.owns_browser:
                    self._send("Browser.close", {}, browser=True)
            except Exception as exc:
                self.emit("browser_close_error", error=str(exc))
            finally:
                self.ws.close()
                self.ws = None
        if self.owns_browser and self.child and self.child.poll() is None:
            try:
                self.child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.child.terminate()
        self.emit("browser_closed")
