"""Trusted native Playwright recording runtime, executed in a Linux namespace."""
from __future__ import annotations

import argparse
import builtins
import contextlib
import functools
import hashlib
import io
import json
import os
from pathlib import Path
import time
import traceback
import types
from urllib.parse import urlsplit

from observation import public_dom, public_response, redact, SECRET_CONTROL_SELECTOR
from script_policy import validate_script, MODULES
from unix_bridge import playwright_proxy


UNKNOWN = {"disposition": "unknown", "effects": {"persistent_state_changed": None,
           "affected_record_count": None}, "ui_claims": [], "unknowns": ["Not yet observed"]}


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.flush()
        os.fsync(out.fileno())


class BoundaryError(RuntimeError):
    pass


class Runtime:
    def __init__(self, config, page, context, output):
        self.page, self.context = page, context
        self.origin = config["origin"]
        self.fixture = config["fixture"]
        self.output = output
        self.limit = config["action_limit"]
        self.actions = 0
        self.next_prediction = None
        self.events = []
        self.responses = []
        self.network_cursor = 0
        self.prediction = None
        self.started = time.monotonic()
        self.inside = False
        self.secret_values = set()
        self.original = {}
        self.events_file = (output / "actions.jsonl").open("x", encoding="utf-8")

    def log(self, item):
        item = redact(item, secrets=self.secret_values)
        self.events.append(item)
        self.events_file.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
        self.events_file.flush()
        os.fsync(self.events_file.fileno())

    def expect(self, prediction, rationale=""):
        if not isinstance(prediction, dict) or prediction.get("disposition") not in {"accepted", "rejected", "unknown"}:
            raise ValueError("expect() needs the registered prediction object")
        self.next_prediction = {"prediction": prediction, "rationale": str(rationale)}

    def note(self, text):
        self.log({"kind": "learner_note", "text": str(text)})

    def network(self):
        result = self.responses[self.network_cursor:]
        self.network_cursor = len(self.responses)
        return redact(result, secrets=self.secret_values)

    def response(self, response):
        try:
            url = response.url
            if urlsplit(url).netloc != urlsplit(self.origin).netloc:
                return
            resource = response.request.resource_type
            media = response.headers.get("content-type", "")
            if resource in {"script", "stylesheet", "image", "font", "media"}:
                return
            body = response.body()
            if len(body) > 2 * 1024 * 1024:
                body = b""
            self.responses.append(public_response(url, response.request.method, response.status, media, body, resource))
        except Exception as error:
            self.responses.append({"body_omitted": "unavailable", "reason": type(error).__name__})

    def observe(self, label="observation"):
        index = sum(e.get("kind") == "observation" for e in self.events) + 1
        stem = f"obs-{index:04d}"
        try:
            self.secret_values.update(self.page.locator(SECRET_CONTROL_SELECTOR).evaluate_all(
                "els => els.map(e => e.value).filter(Boolean)"))
            dom = self.original["Page.content"](self.page)
            (self.output / (stem + ".html")).write_text(
                redact(public_dom(dom), secrets=self.secret_values), encoding="utf-8")
            self.page.screenshot(path=str(self.output / (stem + ".png")), full_page=True,
                                 mask=[self.page.locator(SECRET_CONTROL_SELECTOR)], timeout=10000)
            ax = self.page.accessibility.snapshot(interesting_only=False)
            save(self.output / (stem + ".ax.json"), redact(ax, secrets=self.secret_values))
            text = self.original["Page.inner_text"](self.page, "body", timeout=3000)
            item = {"kind": "observation", "label": str(label), "url": self.page.url,
                    "dom": stem + ".html", "screenshot": stem + ".png", "accessibility": stem + ".ax.json",
                    "visible_text": redact(text[:18000], secrets=self.secret_values), "network": self.network()}
        except Exception as error:
            item = {"kind": "observation", "label": str(label), "error": type(error).__name__ + ": " + str(error)[:1000]}
        self.log(item)
        return redact(item, secrets=self.secret_values)

    def action(self, owner, name, original, args, kwargs):
        if self.inside:
            return original(owner, *args, **kwargs)
        if self.actions >= self.limit:
            raise BoundaryError("registered UI action budget exhausted")
        if name == "goto":
            target = urlsplit(str(args[0] if args else kwargs.get("url", "")))
            if target.scheme not in {"http"} or target.netloc != urlsplit(self.origin).netloc:
                raise BoundaryError("navigation outside the registered website")
            if target.path.lower().endswith((".js", ".mjs", ".map")):
                raise BoundaryError("client-code navigation is outside observations")
        prediction = self.next_prediction
        self.next_prediction = None
        if prediction is None:
            raise BoundaryError("call h.expect(prediction, rationale) before every UI action")
        self.actions += 1
        before = self.observe(f"before-{self.actions}")
        self.log({"kind": "action_before", "action": self.actions, "method": name,
                  "target": str(owner)[:1000], "prediction": prediction["prediction"],
                  "rationale": prediction["rationale"], "observation": before.get("dom")})
        started = time.monotonic()
        self.inside = True
        error = None
        try:
            from playwright.sync_api import Locator
            if isinstance(owner, Locator) and name not in {"scroll_into_view_if_needed"}:
                owner.wait_for(state="visible", timeout=30000)
                owner.scroll_into_view_if_needed(timeout=30000)
            result = original(owner, *args, **kwargs)
            self.page.wait_for_timeout(250)
            return result
        except Exception as exc:
            error = type(exc).__name__ + ": " + str(exc)[:2000]
            raise
        finally:
            self.inside = False
            after = self.observe(f"after-{self.actions}")
            self.log({"kind": "action_after", "action": self.actions, "method": name,
                      "elapsed_seconds": time.monotonic() - started, "error": error,
                      "observation": after.get("dom"), "classification": "unconfirmed"})

    def patch(self):
        from playwright.sync_api import Page, Locator, Keyboard, Mouse
        action_methods = {Page: "goto reload go_back go_forward click dblclick fill type press check uncheck set_checked select_option hover focus",
                          Locator: "click dblclick fill type press check uncheck set_checked select_option hover focus scroll_into_view_if_needed",
                          Keyboard: "press type", Mouse: "click dblclick wheel move"}
        for cls, names in action_methods.items():
            for name in names.split():
                if not hasattr(cls, name):
                    continue
                original = getattr(cls, name)
                @functools.wraps(original)
                def action(owner, *args, fn=original, method=name, **kwargs):
                    if kwargs.get("timeout", 0) > 30000:
                        raise BoundaryError("operation timeout exceeds registration")
                    return self.action(owner, method, fn, args, kwargs)
                setattr(cls, name, action)
        for cls in (Page, Locator):
            for name in ("content", "inner_html", "inner_text", "text_content", "all_text_contents", "all_inner_texts", "get_attribute", "input_value"):
                if not hasattr(cls, name):
                    continue
                original = getattr(cls, name)
                self.original[cls.__name__ + "." + name] = original
                @functools.wraps(original)
                def read(owner, *args, fn=original, method=name, **kwargs):
                    if method == "get_attribute":
                        attr = str(args[-1] if args else kwargs.get("name", "")).lower()
                        if attr.startswith("on") or attr in {"srcdoc", "value"}:
                            raise BoundaryError("active-code or input-value attribute is excluded; use input_value for nonsecret controls")
                    if method in {"inner_html", "inner_text", "text_content", "all_text_contents", "all_inner_texts", "input_value"}:
                        locator = owner if isinstance(owner, Locator) else owner.locator(args[0])
                        forbidden = locator.evaluate_all("els => els.some(e => e.tagName === 'SCRIPT' || (e.tagName === 'INPUT' && /password|token|secret/i.test((e.type||'')+' '+(e.name||''))))")
                        if forbidden:
                            raise BoundaryError("client script or secret control body is excluded")
                        if method in {"text_content", "all_text_contents"}:
                            values = locator.evaluate_all("els => els.map(e => {const c=e.cloneNode(true); c.querySelectorAll('script').forEach(s=>s.remove()); return c.textContent;})")
                            return redact(values if method == "all_text_contents" else (values[0] if values else None))
                    value = fn(owner, *args, **kwargs)
                    if method in {"content", "inner_html"}:
                        return public_dom(value)
                    if method == "get_attribute" and isinstance(value, str) and value.lstrip().lower().startswith("javascript:"):
                        raise BoundaryError("active-code attribute excluded")
                    return redact(value, secrets=self.secret_values)
                setattr(cls, name, read)


def safe_environment(runtime, modules):
    allowed_builtins = "abs all any bool dict enumerate filter float int isinstance len list map max min next print range reversed round set sorted str sum tuple zip Exception ValueError RuntimeError AssertionError KeyError IndexError TypeError StopIteration".split()
    values = {name: getattr(builtins, name) for name in allowed_builtins}
    loaded = {}
    def load_module(name, globals=None, locals=None, fromlist=(), level=0):
        if level:
            raise BoundaryError("relative imports excluded")
        if name in MODULES:
            return __import__(name, globals, locals, fromlist, 0)
        if name not in modules:
            raise BoundaryError("unregistered module")
        if name not in loaded:
            module = types.ModuleType(name)
            module.__dict__["__builtins__"] = values
            loaded[name] = module
            source = modules[name]
            validate_script(source, module_names=modules)
            exec(compile(source, name + ".py", "exec"), module.__dict__)
        return loaded[name]
    values["__import__"] = load_module
    return {"__builtins__": values}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    job_path = Path(args.job)
    job = json.loads(job_path.read_text())
    output = job_path.parent / "evidence"
    output.mkdir()
    source = job["script"]
    modules = job.get("modules", {})
    validate_script(source, module_names=modules)
    for module in modules.values():
        validate_script(module, module_names=modules)
    from playwright.sync_api import sync_playwright
    started = time.monotonic()
    stdout = io.StringIO()
    result = {"status": "error", "error": None, "actions": 0}
    os.environ["HOME"] = str(job_path.parent)
    os.environ["TMPDIR"] = str(job_path.parent)
    with playwright_proxy(job["socket"]) as proxy, sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/browser-meme/browsers/chromium-1117/chrome-linux/chrome",
                                    headless=True, chromium_sandbox=True, proxy=proxy, timeout=30000)
        state = Path(job["state_path"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                      storage_state=str(state) if state.exists() else None)
        context.set_default_timeout(30000)
        context.set_default_navigation_timeout(30000)
        context.tracing.start(screenshots=True, snapshots=True, sources=False)
        page = context.new_page()
        runtime = Runtime(job, page, context, output)
        page.on("response", runtime.response)
        runtime.patch()
        try:
            env = safe_environment(runtime, modules)
            with contextlib.redirect_stdout(stdout):
                exec(compile(source, "learner-script.py", "exec"), env)
                result["return_value"] = redact(env["run"](runtime), secrets=runtime.secret_values)
            result["status"] = "completed"
        except Exception as error:
            result["error"] = type(error).__name__ + ": " + str(error)[:6000]
            result["failure_category"] = "boundary" if isinstance(error, BoundaryError) else "unclassified"
        finally:
            result["last_observation"] = runtime.observe("final")
            result["actions"] = runtime.actions
            result["console"] = redact(stdout.getvalue()[:40000], secrets=runtime.secret_values)
            result["elapsed_seconds"] = time.monotonic() - started
            save(output / "network.json", redact(runtime.responses, secrets=runtime.secret_values))
            result = redact(result, secrets=runtime.secret_values)
            save(output / "result.json", result)
            runtime.events_file.close()
            context.storage_state(path=str(state))
            context.tracing.stop(path=str(job_path.parent / "private-trace.zip"))
            context.close()
            browser.close()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
