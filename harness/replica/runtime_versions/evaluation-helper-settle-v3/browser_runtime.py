"""Trusted native Playwright recording runtime, executed in a Linux namespace."""
from __future__ import annotations

import argparse
import builtins
import contextlib
import functools
import hashlib
import io
import inspect
import json
import os
from pathlib import Path
import time
import traceback
import types
import zipfile
from urllib.parse import urlsplit

from observation import public_dom, public_response, redact, SECRET_CONTROL_SELECTOR, secret_key
from script_policy import validate_script, MODULES
from unix_bridge import playwright_proxy
from trees import capture as capture_trees, canonicalize, POLICY as TREE_POLICY
from settle import run as run_settle, normalize_policy as normalize_settle_policy


UNKNOWN = {"disposition": "unknown", "effects": {"persistent_state_changed": None,
           "affected_record_count": None}, "ui_claims": [], "unknowns": ["Not yet observed"]}


def save(path, value):
    with Path(path).open("x", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.flush()
        os.fsync(out.fileno())


class BoundaryError(RuntimeError):
    pass


class CaptureUnconfirmed(RuntimeError):
    """The preregistered local acquisition bound did not establish stability."""
    pass


class TargetConfirmationError(RuntimeError):
    """Ordinary locator/visibility/state failure; never a permission denial."""
    pass


class NeedsReading(RuntimeError):
    """A controlled observation pause, resumable in a later broker call."""
    pass


class ComparisonStop(RuntimeError):
    """Coordinator stopped this lane after a paired observation."""
    pass


class Runtime:
    def __init__(self, config, page, context, output):
        self.config = config
        self.page, self.context = page, context
        self.origin = config["origin"]
        self.fixture = config["fixture"]
        self.output = output
        self.private_trees = output.parent / "private-trees"
        self.private_trees.mkdir(exist_ok=True)
        self.limit = config["action_limit"]
        self.actions = 0
        self.next_prediction = None
        self.closed_reason = None
        self.read_request = None
        self.capture_unconfirmed = None
        self.pending_stability = None
        self.pending_requests = {}
        self.settle_policy = normalize_settle_policy(config.get("settle_policy"))
        self.events = []
        self.responses = []
        self.network_cursor = 0
        self.prediction = None
        self.started = time.monotonic()
        self.inside = False
        self.secret_values = set()
        self.private_storage_secrets = set()
        self.original = {}
        self.events_file = (output / "actions.jsonl").open("x", encoding="utf-8")

    def log(self, item):
        item = redact(item, secrets=self.secret_values)
        self.events.append(item)
        self.events_file.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
        self.events_file.flush()
        os.fsync(self.events_file.fileno())

    def mark_rejection(self, reason):
        if not self.closed_reason:
            self.closed_reason = str(reason)
            self.log({"kind": "policy_rejection", "stop_reason": self.closed_reason, "time_ns": time.time_ns()})

    def reject(self, reason):
        self.mark_rejection(reason)
        raise BoundaryError(self.closed_reason)

    def expect(self, prediction, rationale=""):
        if self.capture_unconfirmed:
            raise CaptureUnconfirmed(self.capture_unconfirmed["reason"])
        if self.read_request:
            raise NeedsReading(self.read_request["reason"])
        if self.closed_reason:
            self.reject("execution already closed")
        if not isinstance(prediction, dict) or prediction.get("disposition") not in {"accepted", "rejected", "unknown"}:
            raise ValueError("expect() needs the registered prediction object")
        self.next_prediction = {"prediction": prediction, "rationale": str(rationale)}

    def confirm(self, locator):
        from playwright.sync_api import Locator
        if not isinstance(locator, Locator):
            raise TargetConfirmationError("confirm requires a native Playwright Locator")
        if locator.count() != 1:
            raise TargetConfirmationError("target must resolve to exactly one element; found " + str(locator.count()))
        previous = self.inside
        self.inside = True
        try:
            try:
                locator.wait_for(state="visible", timeout=30000)
                locator.scroll_into_view_if_needed(timeout=30000)
            except Exception as error:
                raise TargetConfirmationError("target visibility/scroll not confirmed: " + str(error)[:1000]) from error
            if not locator.is_enabled():
                raise TargetConfirmationError("target is not enabled")
            identity = locator.evaluate("e => ({tag:e.tagName,role:e.getAttribute('role'),id:e.id,name:e.getAttribute('name'),type:e.getAttribute('type'),label:e.getAttribute('aria-label'),text:(e.innerText||'').slice(0,1000)})")
        finally:
            self.inside = previous
        self.log({"kind": "target_confirmed", "action": self.actions, "identity": identity, "url": self.page.url})
        return identity

    def read_point(self, reason):
        observation = self.observe("read-point")
        source_location = None
        caller = inspect.currentframe().f_back
        while caller is not None:
            if caller.f_code.co_filename == "learner-script.py":
                source_location = {"file":"script.py", "line":caller.f_lineno}
                break
            caller = caller.f_back
        del caller
        result = {"status":"needs_reading", "reason":str(reason), "observation":observation, "source_location":source_location}
        self.log({"kind":"read_point", "reason":str(reason), "observation":observation, "source_location":source_location})
        self.read_request = result
        raise NeedsReading(str(reason))

    def classify(self, disposition, explanation=""):
        if disposition not in {"matches_prediction", "contradiction", "unconfirmed"}:
            raise ValueError("classification must name matches_prediction, contradiction or unconfirmed")
        self.log({"kind": "learner_classification", "action": self.actions, "classification": disposition, "explanation": str(explanation)})

    def note(self, text):
        self.log({"kind": "learner_note", "text": str(text)})

    def network(self):
        result = self.responses[self.network_cursor:]
        self.network_cursor = len(self.responses)
        return redact(result, secrets=self.secret_values)

    def request_started(self, request):
        self.pending_requests[id(request)] = request

    def request_finished(self, request):
        self.pending_requests.pop(id(request), None)

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

    def collect_private_control_state(self, tree_directory):
        """Opt-in, read-only management evidence; never part of public observe()."""
        try:
            state = self.page.evaluate("""() => {
              const read = storage => {
                const entries = [];
                for (let i=0; i<storage.length; i++) {
                  const key = storage.key(i);
                  if (key !== null) entries.push([key, storage.getItem(key)]);
                }
                return entries;
              };
              return {url:location.href, local_storage:read(window.localStorage),
                      session_storage:read(window.sessionStorage)};
            }""")
            for field in ("local_storage", "session_storage"):
                state[field] = dict(state[field])
                for key, value in state[field].items():
                    if secret_key(key) and isinstance(value, str) and value:
                        self.secret_values.add(value)
                        self.private_storage_secrets.add(value)
        except Exception as error:
            state = {"url":self.page.url, "local_storage":None, "session_storage":None,
                     "error":type(error).__name__ + ": " + str(error)[:2000]}
        save(tree_directory / "control-state.json", state)

    def observe(self, label="observation"):
        index = sum(e.get("kind") == "observation" for e in self.events) + 1
        stem = f"obs-{index:04d}"
        try:
            tree_directory = self.private_trees / stem
            tree_directory.mkdir()
            if self.config.get("collect_private_control_state", False):
                self.collect_private_control_state(tree_directory)
            secret_locators = [frame.locator(SECRET_CONTROL_SELECTOR) for frame in self.page.frames]
            for secret_locator in secret_locators:
                self.secret_values.update(secret_locator.evaluate_all("els => els.map(e => e.value).filter(Boolean)"))
            dom = self.original["Page.content"](self.page)
            (self.output / (stem + ".html")).write_text(
                redact(public_dom(dom), secrets=self.secret_values), encoding="utf-8")
            self.page.screenshot(path=str(self.output / (stem + ".png")), full_page=True, caret="initial",
                                 mask=secret_locators + [frame.get_by_text(value, exact=False) for frame in self.page.frames for value in self.private_storage_secrets], timeout=10000)
            trees = capture_trees(self.page)
            if self.pending_stability:
                self.finish_stability(trees)
            trees["raw"] = redact(trees["raw"], secrets=self.secret_values)
            save(tree_directory / "raw.json", trees["raw"])
            save(tree_directory / "canonical.json", canonicalize(trees["raw"]))
            save(tree_directory / "normalization.json", {"policy": TREE_POLICY, "secret_values": "redacted before persistence; applies to raw and canonical trees"})
            ax = [{"frame": frame.get("frame_id", frame.get("url")), "ax": frame.get("ax")} for frame in trees["raw"].get("frames", [])]
            save(self.output / (stem + ".ax.json"), redact(ax, secrets=self.secret_values))
            text = self.original["Page.inner_text"](self.page, "body", timeout=3000)
            item = {"kind": "observation", "label": str(label), "url": self.page.url,
                    "dom": stem + ".html", "screenshot": stem + ".png", "accessibility": stem + ".ax.json",
                    "projection": {"dom": "script_elements_and_active_attributes_removed_secret_values_redacted", "ax": "CDP_Accessibility_getFullAXTree_secret_values_redacted"},
                    "visible_text": redact(text[:18000], secrets=self.secret_values), "network": self.network()}
        except Exception as error:
            if self.pending_stability:
                self.finish_stability(None, "checkpoint_observation_failure")
            item = {"kind": "observation", "label": str(label), "error": type(error).__name__ + ": " + str(error)[:1000]}
        self.log(item)
        return redact(item, secrets=self.secret_values)

    def persist_stability(self, record):
        path = self.output.parent / "settle-status.json"
        temporary = path.with_name(path.name + ".next")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        temporary.replace(path)

    def finish_stability(self, snapshot, failure=None):
        record = self.pending_stability
        now = time.monotonic()
        if snapshot is not None:
            canonical = canonicalize(snapshot["raw"])
            digest = hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
            record["checkpoint_verification_sha256"] = digest
            if canonical.get("unsupported"):
                failure = "unsupported_checkpoint_acquisition"
            elif digest != record["samples"][-1]["canonical_sha256"]:
                failure = "changed_after_stability_before_checkpoint"
        if self.pending_requests:
            failure = "network_resumed_before_checkpoint"
        if now > record["deadline_monotonic"]:
            failure = "total_timeout_during_checkpoint_acquisition"
        record.update(status="unconfirmed" if failure else "stable", elapsed_seconds=now-record["started_monotonic"])
        if failure:
            record["reason"] = failure
            self.capture_unconfirmed = record
        self.persist_stability(record)
        self.pending_stability = None
        self.log({"kind":"capture_stability", **record})

    def settle(self, label, source_location=None):
        if self.closed_reason:
            return {"enabled":self.settle_policy["enabled"], "status":"skipped_policy_denial", "reason":self.closed_reason}
        if self.capture_unconfirmed:
            return self.capture_unconfirmed
        record = run_settle(self.page, self.settle_policy, capture_trees, canonicalize,
                            self.output.parent / "settle-status.json", label=label,
                            action=self.actions, source_location=source_location, pending_requests=lambda:len(self.pending_requests))
        self.log({"kind":"capture_stability_samples", **record})
        if record["status"] == "stable":
            self.pending_stability = record
            self.persist_stability({**record, "status":"running", "phase":"checkpoint_verification"})
        if record["status"] == "unconfirmed":
            self.capture_unconfirmed = record
        return record

    def barrier(self, event, checkpoint=None):
        directory = self.config.get("step_barrier_dir")
        if not directory:
            return
        root = Path(directory)
        stem = checkpoint or "step-" + str(self.actions).zfill(4)
        checkpoint_kind = checkpoint or "after_action"
        item = {**event, "checkpoint":checkpoint_kind, "method":event.get("method", checkpoint_kind),
                "action_arguments":event.get("action_arguments", {"args":event.get("call_args", []), "kwargs":event.get("call_kwargs", {})}),
                "evidence_directory":str(self.output), "private_trees_directory":str(self.private_trees), "action":self.actions}
        save(root / (stem + ".json"), redact(item, secrets=self.secret_values))
        release = root / (stem + ".release.json")
        deadline = time.monotonic() + min(60, float(self.config.get("step_barrier_timeout_seconds", 60)))
        while not release.exists():
            if time.monotonic() >= deadline:
                raise ComparisonStop("comparison_barrier_timeout")
            self.page.wait_for_timeout(50)
        value = json.loads(release.read_text(encoding="utf-8"))
        decision = value.get("decision", value.get("command", value.get("action")))
        if decision == "stop":
            raise ComparisonStop("comparison_difference_stop:" + str(value.get("reason", "unspecified")))
        if decision != "continue":
            raise ComparisonStop("comparison_invalid_release")

    def action(self, owner, name, original, args, kwargs):
        if self.capture_unconfirmed:
            raise CaptureUnconfirmed(self.capture_unconfirmed["reason"])
        if self.read_request:
            raise NeedsReading(self.read_request["reason"])
        if self.closed_reason:
            self.reject("execution already closed")
        if self.inside:
            return original(owner, *args, **kwargs)
        if self.actions >= self.limit:
            self.reject("registered UI action budget exhausted")
        if name == "goto":
            target = urlsplit(str(args[0] if args else kwargs.get("url", "")))
            if target.scheme not in {"http"} or target.netloc != urlsplit(self.origin).netloc:
                self.reject("navigation outside the registered website")
            if target.path.lower().endswith((".js", ".mjs", ".map")):
                self.reject("client-code navigation is outside observations")
        prediction = self.next_prediction
        self.next_prediction = None
        if prediction is None:
            self.reject("call h.expect(prediction, rationale) before every UI action")
        source_location = None
        caller = inspect.currentframe()
        while caller is not None:
            if caller.f_code.co_filename == "learner-script.py":
                source_location = {"file": "script.py", "line": caller.f_lineno}
                break
            caller = caller.f_back
        del caller
        from playwright.sync_api import Page, Locator
        locator_target = owner if isinstance(owner, Locator) else None
        if isinstance(owner, Page) and name not in {"goto", "reload", "go_back", "go_forward"}:
            selector = args[0] if args else kwargs.get("selector")
            if selector is not None:
                locator_target = owner.locator(selector)
        secret_target = locator_target
        if secret_target is None and type(owner).__name__ == "Keyboard":
            secret_target = self.page.locator(":focus")
        if name in {"fill", "type", "press"} and secret_target is not None:
            secret_control = secret_target.evaluate_all("els => els.some(e => /password|token|secret/i.test((e.type||'')+' '+(e.name||'')+' '+(e.autocomplete||'')))")
            if secret_control:
                value_index = 1 if isinstance(owner, Page) else 0
                value = args[value_index] if len(args) > value_index else kwargs.get("value", kwargs.get("text", ""))
                if isinstance(value, str) and value:
                    self.secret_values.add(value)
        def serializable(value):
            if value is None or isinstance(value, (str, bool, int, float)):
                return value
            if isinstance(value, (list, tuple)):
                return [serializable(item) for item in value]
            if isinstance(value, dict):
                return {str(key):serializable(item) for key,item in value.items()}
            return {"non_json_type":type(value).__name__}
        call_args, call_kwargs = serializable(args), serializable(kwargs)
        action_identity = {"owner":type(owner).__name__, "method":name, "target":str(owner)[:1000], "element":None}
        self.actions += 1
        before = self.observe(f"before-{self.actions}")
        self.log({"kind": "action_before", "action": self.actions, "method": name,
                  "target": str(owner)[:1000], "prediction": prediction["prediction"], "source_location": source_location, "action_id": self.actions,
                  "action_identity":action_identity, "call_args":call_args, "call_kwargs":call_kwargs,
                  "target_confirmation": {"url": self.page.url, "locator": str(owner)[:1000]},
                  "rationale": prediction["rationale"], "observation": before.get("dom")})
        started = time.monotonic()
        self.inside = True
        error = None
        try:
            if locator_target is not None:
                action_identity["element"] = self.confirm(locator_target)
            result = original(owner, *args, **kwargs)
            self.page.wait_for_timeout(250)
            return result
        except Exception as exc:
            error = type(exc).__name__ + ": " + str(exc)[:2000]
            raise
        finally:
            self.inside = False
            stability = self.settle("after-action", source_location)
            after = self.observe(f"after-{self.actions}")
            event = {"kind": "action_after", "action": self.actions, "action_id": self.actions, "method": name,
                     "action_identity":action_identity, "call_args":call_args, "call_kwargs":call_kwargs,
                     "stability":stability, "status":"unconfirmed" if self.capture_unconfirmed else "observed",
                     "prediction": prediction["prediction"], "source_location": source_location, "elapsed_seconds": time.monotonic() - started, "error": error,
                     "observation": after, "classification": "unconfirmed"}
            self.log(event)
            try:
                self.barrier(event)
            finally:
                if self.capture_unconfirmed:
                    raise CaptureUnconfirmed(self.capture_unconfirmed["reason"])

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
                        self.reject("operation timeout exceeds registration")
                    return self.action(owner, method, fn, args, kwargs)
                setattr(cls, name, action)
        original_wait_for_url = Page.wait_for_url
        def wait_for_url(owner, url, **kwargs):
            if self.closed_reason:
                self.reject("execution already closed")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                target = urlsplit(url)
                allowed = urlsplit(self.origin)
                if target.scheme != allowed.scheme or target.netloc != allowed.netloc:
                    self.reject("wait_for_url outside the registered website")
            if kwargs.get("timeout", 0) > 30000:
                self.reject("operation timeout exceeds registration")
            return original_wait_for_url(owner, url, **kwargs)
        Page.wait_for_url = wait_for_url
        for cls in (Page, Locator):
            for name in ("content", "inner_html", "inner_text", "text_content", "all_text_contents", "all_inner_texts", "get_attribute", "input_value", "aria_snapshot"):
                if not hasattr(cls, name):
                    continue
                original = getattr(cls, name)
                self.original[cls.__name__ + "." + name] = original
                @functools.wraps(original)
                def read(owner, *args, fn=original, method=name, **kwargs):
                    if method == "get_attribute":
                        attr = str(args[-1] if args else kwargs.get("name", "")).lower()
                        if attr.startswith("on") or attr in {"srcdoc", "value"}:
                            self.reject("active-code or input-value attribute is excluded; use input_value for nonsecret controls")
                    if method in {"inner_html", "inner_text", "text_content", "all_text_contents", "all_inner_texts", "input_value"}:
                        locator = owner if isinstance(owner, Locator) else owner.locator(args[0])
                        forbidden = locator.evaluate_all("els => els.some(e => e.tagName === 'SCRIPT' || (e.tagName === 'INPUT' && /password|token|secret/i.test((e.type||'')+' '+(e.name||'')+' '+(e.autocomplete||''))))")
                        if forbidden:
                            self.reject("client script or secret control body is excluded")
                        if method in {"text_content", "all_text_contents"}:
                            values = locator.evaluate_all("els => els.map(e => {const c=e.cloneNode(true); c.querySelectorAll('script').forEach(s=>s.remove()); return c.textContent;})")
                            return redact(values if method == "all_text_contents" else (values[0] if values else None))
                    value = fn(owner, *args, **kwargs)
                    if method in {"content", "inner_html"}:
                        return public_dom(value)
                    if method == "get_attribute" and isinstance(value, str) and value.lstrip().lower().startswith("javascript:"):
                        self.reject("active-code attribute excluded")
                    return redact(value, secrets=self.secret_values)
                setattr(cls, name, read)


def safe_environment(runtime, modules):
    allowed_builtins = "abs all any bool dict enumerate filter float int isinstance len list map max min next print range reversed round set sorted str sum tuple zip Exception ValueError RuntimeError AssertionError KeyError IndexError TypeError StopIteration".split()
    values = {name: getattr(builtins, name) for name in allowed_builtins}
    loaded = {}
    def load_module(name, globals=None, locals=None, fromlist=(), level=0):
        if level:
            runtime.reject("relative imports excluded")
        if name in MODULES:
            return __import__(name, globals, locals, fromlist, 0)
        if name not in modules:
            runtime.reject("unregistered module")
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
    with playwright_proxy(job["socket"]) as proxy, sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/lib/chromium/chromium",
                                    headless=True, chromium_sandbox=False, proxy=proxy, timeout=30000)
        state = Path(job["state_path"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                      storage_state=str(state) if state.exists() else None)
        if job.get("init_script"):
            context.add_init_script(script=job["init_script"])
        context.set_default_timeout(30000)
        context.set_default_navigation_timeout(30000)
        context.tracing.start(screenshots=False, snapshots=True, sources=False)
        page = context.new_page()
        def enforce_origin(route):
            target = urlsplit(route.request.url)
            allowed = urlsplit(job["origin"])
            if target.scheme == allowed.scheme and target.netloc == allowed.netloc:
                route.continue_()
            else:
                runtime.mark_rejection("browser request outside the registered origin: " + route.request.url)
                route.abort("blockedbyclient")
        context.route("**/*", enforce_origin)
        runtime = Runtime(job, page, context, output)
        page.on("request", runtime.request_started)
        page.on("requestfinished", runtime.request_finished)
        page.on("requestfailed", runtime.request_finished)
        page.on("response", runtime.response)
        runtime.patch()
        try:
            if job.get("state_barriers"):
                if job.get("initial_url"):
                    initial = urlsplit(job["initial_url"])
                    allowed = urlsplit(job["origin"])
                    if initial.scheme != allowed.scheme or initial.netloc != allowed.netloc:
                        runtime.reject("initial_url outside the registered website")
                    runtime.log({"kind":"trusted_initial_navigation", "url":job["initial_url"], "counts_as_business_action":False})
                    runtime.inside = True
                    try:
                        page.goto(job["initial_url"])
                        page.wait_for_timeout(250)
                    finally:
                        runtime.inside = False
                stability = runtime.settle("state0")
                try:
                    runtime.barrier({"kind":"state0", "observation":runtime.observe("state0"), "status":"unconfirmed" if runtime.capture_unconfirmed else "ready", "stability":stability, "action":0}, checkpoint="state0")
                finally:
                    if runtime.capture_unconfirmed:
                        raise CaptureUnconfirmed(runtime.capture_unconfirmed["reason"])
            env = safe_environment(runtime, modules)
            with contextlib.redirect_stdout(stdout):
                exec(compile(source, "learner-script.py", "exec"), env)
                result["return_value"] = redact(env["run"](runtime), secrets=runtime.secret_values)
            result["status"] = "completed"
            if isinstance(result.get("return_value"), dict) and result["return_value"].get("status") == "needs_reading":
                runtime.read_request = result["return_value"]
            if runtime.closed_reason:
                result.update(status="error", error="BoundaryError: " + runtime.closed_reason, failure_category="boundary")
            elif runtime.capture_unconfirmed:
                result.update(status="unconfirmed", failure_category="capture_stability", stability=runtime.capture_unconfirmed)
            elif runtime.read_request:
                result.update(status="needs_reading", reading_request=runtime.read_request)
        except CaptureUnconfirmed:
            result.update(status="unconfirmed", failure_category="capture_stability", stability=runtime.capture_unconfirmed)
        except NeedsReading:
            result.update(status="needs_reading", reading_request=runtime.read_request)
        except Exception as error:
            result["error"] = type(error).__name__ + ": " + str(error)[:6000]
            result["failure_category"] = "boundary" if isinstance(error, BoundaryError) else "localization" if isinstance(error, TargetConfirmationError) else "comparison_stop" if isinstance(error, ComparisonStop) else "unclassified"
            if isinstance(error, ComparisonStop):
                result["status"] = "stopped"
        finally:
            stability = runtime.settle("final")
            if runtime.closed_reason:
                result.update(status="error", error="BoundaryError: " + runtime.closed_reason, failure_category="boundary")
            elif runtime.capture_unconfirmed:
                result.update(status="unconfirmed", failure_category="capture_stability", stability=runtime.capture_unconfirmed)
            result["last_observation"] = runtime.observe("final")
            if runtime.capture_unconfirmed and not runtime.closed_reason:
                result.update(status="unconfirmed", failure_category="capture_stability", stability=runtime.capture_unconfirmed)
            if job.get("state_barriers"):
                try:
                    runtime.barrier({"kind":"final", "observation":result["last_observation"], "status":result["status"], "stability":stability, "reading_request":runtime.read_request, "source_location":(runtime.read_request or {}).get("source_location"), "error":result.get("error")}, checkpoint="final")
                except ComparisonStop as error:
                    result["comparison_stop"] = str(error)
                    if result["status"] == "completed":
                        result.update(status="stopped", failure_category="comparison_stop")
            result["actions"] = runtime.actions
            result["console"] = redact(stdout.getvalue()[:40000], secrets=runtime.secret_values)
            result["elapsed_seconds"] = time.monotonic() - started
            save(output / "network.json", redact(runtime.responses, secrets=runtime.secret_values))
            result = redact(result, secrets=runtime.secret_values)
            save(output / "result.json", result)
            runtime.events_file.close()
            context.storage_state(path=str(state))
            raw_trace = job_path.parent / "transient-trace.zip"
            context.tracing.stop(path=str(raw_trace))
            try:
                with zipfile.ZipFile(raw_trace) as archive, zipfile.ZipFile(job_path.parent / "private-trace.zip", "x", compression=zipfile.ZIP_DEFLATED) as sanitized:
                    for info in archive.infolist():
                        data = archive.read(info)
                        if not info.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                            try:
                                data = redact(data.decode("utf-8"), secrets=runtime.secret_values).encode("utf-8")
                            except UnicodeDecodeError:
                                # Opaque trace resources are not needed for DOM/AX
                                # correctness and cannot be certified secret-free.
                                continue
                        sanitized.writestr(info, data)
            finally:
                raw_trace.unlink(missing_ok=True)
            context.close()
            browser.close()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
