"""Protocol 2: supervise independently authored native Playwright scripts.

This module contains no target-website rules, selectors or business actions.
The worker is trusted local code, not an operating-system sandbox.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
from urllib.parse import urlparse
import uuid
import zipfile

from .artifacts import Recorder as BaseRecorder, digest, write_json as raw_write_json
from .checks import evaluate_step
from .contract import canonical_cases, local_path, read_json, require, validate_check

ROOT = Path(__file__).resolve().parents[1]
LIMITS = {"case_seconds": 180, "run_seconds": 1800, "command_ms": 30000,
          "cases": 24, "steps": 300}
SECRET_KEYS = {"authorization", "proxy-authorization", "cookie", "set-cookie",
               "access_token", "refresh_token", "password", "password_hash",
               "jwt_secret", "client_secret", "token"}
JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
KNOWN_SECRETS = set()


def remember_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS and isinstance(item, str) and len(item) >= 4:
                KNOWN_SECRETS.add(item)
            else:
                remember_secrets(item)
    elif isinstance(value, list):
        for item in value:
            remember_secrets(item)


def redact(value):
    """Retain observation structure while removing credentials and JWT values."""
    if isinstance(value, dict):
        # HAR/trace headers and cookies use name/value pairs.
        if str(value.get("name", "")).lower() in SECRET_KEYS:
            return {k: "[REDACTED]" if k == "value" else redact(v) for k, v in value.items()}
        output = {}
        password_action = "password" in str(value.get("selector", "")).lower()
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS or (password_action and key in ("value", "text")):
                output[key] = "[REDACTED]"
            elif key == "cookies" and isinstance(item, list):
                output[key] = [{k: "[REDACTED]" if k == "value" else redact(v)
                                for k, v in cookie.items()} for cookie in item]
            else:
                output[key] = redact(item)
        return output
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        cleaned = JWT.sub("[REDACTED-JWT]", value)
        for secret in sorted(KNOWN_SECRETS, key=len, reverse=True):
            cleaned = cleaned.replace(secret, "[REDACTED]")
        cleaned = re.sub(r'((?:[?&]|\b)(?:access_token|refresh_token|password|token|client_secret)=)[^&\s"\'<>]*',
                         r"\1[REDACTED]", cleaned, flags=re.I)
        def mask_input(match):
            tag = match.group(0)
            if re.search(r'(?:type|name)\s*=\s*["\'][^"\']*(?:password|token|secret)', tag, re.I):
                return re.sub(r'(value\s*=\s*)(["\']).*?\2', r'\1"[REDACTED]"', tag, flags=re.I | re.S)
            return tag
        cleaned = re.sub(r"<input\b[^>]*>", mask_input, cleaned, flags=re.I | re.S)
        # Some trace resources encode a JSON body inside a string.
        if cleaned.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(cleaned)
                return json.dumps(redact(parsed), ensure_ascii=False)
            except (ValueError, TypeError):
                pass
        return cleaned
    return value


def write_json(path, value):
    raw_write_json(path, redact(value))


class Recorder(BaseRecorder):
    def emit(self, kind, **data):
        return super().emit(kind, **redact(data))


def all_steps_matched(case, results):
    return [s["id"] for s in results] == [s["id"] for s in case["steps"]] and all(
        s.get("status") == "matched" for s in results)


class ScriptContext:
    """Public UI facade; reflection is outside this trusted-code convention."""
    __slots__ = ("page", "base_url", "case", "step", "confirm", "read_ui")

    def __init__(self, monitor):
        self.page, self.base_url, self.case = monitor.page, monitor.base_url, monitor.case
        self.step, self.confirm, self.read_ui = monitor.step, monitor.confirm, monitor.read_ui


def invoke_script(script, case, monitor):
    # The author may consult its own frozen plan. Never pass a mutable reference
    # to the monitor's plan, and never include independent backend observations.
    script.run(copy.deepcopy(case), ScriptContext(monitor))


def sanitize_trace(source: Path, target: Path):
    """Keep a usable trace ZIP; sanitize JSON entries and response resources."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED) as output:
        for info in original.infolist():
            data = original.read(info.filename)
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                output.writestr(info.filename, data)
                continue
            lines = []
            for line in text.splitlines(keepends=True):
                try:
                    lines.append(json.dumps(redact(json.loads(line)), ensure_ascii=False) + "\n")
                except (ValueError, TypeError):
                    lines.append(redact(line))
            output.writestr(info.filename, "".join(lines).encode("utf-8"))


def module_from(path: Path):
    spec = importlib.util.spec_from_file_location("experiment_" + uuid.uuid4().hex, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_inputs(site, cases, rules, plan):
    require(site.get("site_id") and site.get("adapter") and site.get("source_roots"), "site metadata incomplete")
    require(urlparse(site["base_url"]).hostname in ("localhost", "127.0.0.1", "::1"), "local site required")
    require(set(site["allowed_hosts"]) <= {"localhost", "127.0.0.1", "::1"}, "only local site hosts")
    require(plan.get("schema_version") == 2, "native script plan must use schema_version 2")
    require(plan.get("model") == "gpt-6.1-sol", "user-selected experiment author must be gpt-6.1-sol")
    require(plan.get("revision"), "missing plan revision")
    require(canonical_cases(cases) == canonical_cases(plan["cases"]), "fixed cases changed")
    require(0 < len(cases) <= LIMITS["cases"], "case budget exceeded")
    require(len({c["id"] for c in cases}) == len(cases), "duplicate case ids")
    rule_ids = {r["id"] for r in rules}
    require(len(rule_ids) == len(rules) and rules, "empty/duplicate rules")
    for rule in rules:
        for key in ("statement", "source_refs", "preconditions", "branches", "forbidden_side_effects", "status"):
            require(key in rule, "rule missing " + key)
        require(rule["source_refs"], "rules need source evidence")
    total = 0
    for case in plan["cases"]:
        require(case.get("steps"), "empty script plan")
        require(len({s["id"] for s in case["steps"]}) == len(case["steps"]), "duplicate step ids")
        for step in case["steps"]:
            total += 1
            require(step.get("rule_ids") and set(step["rule_ids"]) <= rule_ids, "unknown rule")
            require(step.get("action"), "missing action description")
            require(step.get("expect"), "missing prediction")
            require(len({b["id"] for b in step["expect"]}) == len(step["expect"]), "duplicate branches")
            for branch in step["expect"]:
                require(branch.get("checks"), "empty branch checks")
                for check in branch["checks"]:
                    validate_check(check)
            for check in step.get("invariants", []):
                validate_check(check)
    require(total <= LIMITS["steps"], "step budget exceeded")
    return {"cases": len(cases), "steps": total, "rules": len(rules)}


def observed_ui(page, readouts, network, network_start=0):
    result = {"url": page.url, "title": page.title(),
              "text": page.locator("body").inner_text() if page.locator("body").count() else "",
              "fields": {}, "errors": {}}
    for name, spec in readouts.items():
        loc = page.locator(spec["selector"])
        try:
            kind = spec["kind"]
            count = loc.count()
            if kind == "count":
                value = count
            elif kind == "visible":
                value = any(loc.nth(i).is_visible() for i in range(count))
            else:
                require(count == 1, f"readout expected 1 match, got {count}")
                if kind == "text":
                    value = loc.inner_text(timeout=1000)
                elif kind == "value":
                    value = loc.input_value(timeout=1000)
                elif kind == "checked":
                    value = loc.is_checked(timeout=1000)
                elif kind == "attr":
                    value = loc.get_attribute(spec["attribute"], timeout=1000)
                else:
                    raise ValueError("unsupported readout " + kind)
            result["fields"][name] = value
        except Exception as exc:
            result["fields"][name] = None
            result["errors"][name] = str(exc)
    result["network"] = redact(network.copy())
    result["step_network"] = redact(network[network_start:])
    return result


class StepMismatch(RuntimeError):
    pass


class ScriptHarness:
    """Public script object with native Page and durable action boundaries."""

    def __init__(self, page, case, plan, adapter, out, recorder, network, base_url):
        self.page = page
        self.case = canonical_cases([case])[0]
        self.base_url = base_url
        self._case_plan = case
        self._plan = plan
        self._adapter = adapter
        self._out = out
        self._recorder = recorder
        self._network = network
        self._next = 0
        self._active = None
        self.results = []
        self.history = []
        self.initial = self._observe()
        self.current = self.initial
        write_json(out / "initial.json", self.initial)
        self._capture("initial")

    def _observe(self, network_start=0):
        result, errors = {}, {}
        for channel, capture in (
            ("ui", lambda: observed_ui(self.page, self._plan.get("readouts", {}), self._network, network_start)),
            ("backend", self._adapter.observe),
        ):
            try:
                result[channel] = capture()
                self._recorder.emit("observation_channel", channel=channel, observation=result[channel])
            except Exception as exc:
                errors[channel] = str(exc)
        if callable(getattr(self._adapter, "observe_ui", None)):
            try:
                result["independent_ui"] = self._adapter.observe_ui(self.page)
                self._recorder.emit("observation_channel", channel="independent_ui", observation=result["independent_ui"])
            except Exception as exc:
                errors["independent_ui"] = str(exc)
        if errors:
            result["observation_errors"] = errors
            self._recorder.emit("observation_errors", errors=errors)
        return result

    def read_ui(self):
        return observed_ui(self.page, self._plan.get("readouts", {}), self._network)

    def confirm(self, locator):
        require(self._active is not None, "confirmation must be inside a predicted step")
        count = locator.count()
        self._recorder.emit("confirm_target", step=self._active, locator=str(locator), count=count)
        if count != 1:
            raise RuntimeError(f"locator: expected exactly one target, got {count}: {locator}")
        locator.scroll_into_view_if_needed()
        self._recorder.emit("scroll_into_view", step=self._active, locator=str(locator))
        if not locator.is_visible() or not locator.is_enabled():
            raise RuntimeError(f"locator: target not visible/enabled: {locator}")
        attributes = locator.evaluate("""e => ({
            tag: e.tagName, attributes: Object.fromEntries([...e.attributes].map(a=>[a.name,a.value])),
            text: e.innerText, type: e.type, bounding: e.getBoundingClientRect().toJSON()
        })""")
        self._recorder.emit("target_ready", step=self._active, locator=str(locator), element=redact(attributes))
        return locator

    def _capture(self, name):
        # DOM from every frame, without inventing element identifiers.
        frames, errors = [], {}
        for frame in self.page.frames:
            try:
                frames.append({"url": frame.url, "name": frame.name, "html": frame.content()})
            except Exception as exc:
                errors[frame.url] = str(exc)
        for cookie in self.page.context.cookies():
            if len(cookie["value"]) >= 4:
                KNOWN_SECRETS.add(cookie["value"])
        write_json(self._out / f"{name}.dom.json", redact(frames))
        try:
            self.page.screenshot(path=str(self._out / f"{name}.png"), full_page=True,
                                 mask=[self.page.locator('input[type="password"], input[name*="token" i], input[name*="secret" i]')])
        except Exception as exc:
            errors["screenshot"] = str(exc)
        if errors:
            write_json(self._out / f"{name}.capture-errors.json", errors)
            raise RuntimeError(f"unconfirmed: evidence capture incomplete: {errors}")

    @contextmanager
    def step(self, step_id):
        require(self._active is None, "nested steps not supported")
        require(self._next < len(self._case_plan["steps"]), "unplanned step")
        step = self._case_plan["steps"][self._next]
        require(step["id"] == step_id, f"step order mismatch: expected {step['id']}, got {step_id}")
        name = f"{self._next + 1:02d}"
        self._next += 1
        self._active = step_id
        before = self._observe()
        require(not before.get("observation_errors"), "unconfirmed: incomplete observation before dispatch")
        network_start = len(self._network)
        result = {"id": step_id, "status": "error", "evidence": f"{name}.json", "screenshot": f"{name}.png"}
        self.results.append(result)
        self._recorder.emit("prediction", step=step_id, action=step["action"], rule_ids=step["rule_ids"],
                            expect=step["expect"], invariants=step.get("invariants", []), before=before)
        self._recorder.emit("action_dispatch", step=step_id)
        started = time.monotonic()
        error = None
        try:
            yield
            result["action_completed"] = True
            self._recorder.emit("action_complete", step=step_id)
        except BaseException as exc:
            error = exc
            result.update(error=str(exc), error_type=type(exc).__name__)
        try:
            after = self._observe(network_start)
            self.current = after
            self.history.append({"step_id": step_id, "before": before, "after": after})
            write_json(self._out / f"{name}.json", {"before": before, "after": after})
            self._capture(name)
            checks = evaluate_step(step, before, after)
            if after.get("observation_errors"):
                checks["status"] = "unconfirmed"
            if error:
                result["prediction_after_error"] = checks
            else:
                result.update(checks)
        except Exception as capture_error:
            result.update(status="unconfirmed", capture_error=str(capture_error))
            if error is None:
                error = capture_error
        result["elapsed_seconds"] = time.monotonic() - started
        self._recorder.emit("step_result", step=step_id, result=result)
        self._active = None
        if error:
            raise error
        if result["status"] != "matched":
            raise StepMismatch(result["status"] + ": " + step_id)


def capture_response(response, network, recorder):
    request = response.request
    entry = {"url": response.url, "method": request.method, "status": response.status,
             "resource_type": request.resource_type, "time_ns": time.time_ns(),
             "content_type": response.headers.get("content-type", "")}
    if request.resource_type in ("fetch", "xhr"):
        try:
            body = request.post_data_json if request.post_data else None
            remember_secrets(body)
            entry["request_json"] = redact(body)
        except Exception:
            entry["request_body_omitted"] = True
        if "json" in entry["content_type"]:
            try:
                body = response.json()
                remember_secrets(body)
                entry["response_json"] = redact(body)
            except Exception as exc:
                entry["body_error"] = str(exc)
    network.append(entry)
    recorder.emit("network_response", response=entry)


def remember_request(request):
    """Observe sensitive values before any trace export, without persisting them."""
    try:
        body = request.post_data_json
        remember_secrets(body)
    except Exception:
        from urllib.parse import parse_qsl
        try:
            remember_secrets(dict(parse_qsl(request.post_data or "")))
        except Exception:
            pass


def run_worker(out: Path, index: int):
    """One owned browser/process per case; parent enforces a hard time budget."""
    site = read_json(out / "inputs/site.json")
    plan = read_json(out / "inputs/plan.json")
    case = plan["cases"][index]
    case_out = out / "cases" / f"{index + 1:02d}-{case['id']}"
    case_out.mkdir(parents=True, exist_ok=False)
    recorder = Recorder(case_out / "events.jsonl")
    result = {"id": case["id"], "passed": False, "status": "blocked", "steps": [], "independent_checks": []}
    start = time.monotonic()
    browser = context = playwright = harness = None
    raw_trace = ROOT / ".runtime/trace-private" / (uuid.uuid4().hex + ".zip")
    raw_trace.parent.mkdir(parents=True, exist_ok=True)
    phase = "setup"
    try:
        os.environ.update(site.get("runtime_env", {}))
        adapter = module_from(local_path(ROOT, site["adapter"]))
        recorder.emit("reset_start", case=canonical_cases([case])[0])
        result["setup"] = adapter.reset(canonical_cases([case])[0])
        recorder.emit("reset_complete", setup=result["setup"])
        phase = "browser_start"
        from playwright.sync_api import sync_playwright
        playwright = sync_playwright().start()
        executable = os.environ.get("HARNESS_CHROME")
        options = {"headless": True, "timeout": LIMITS["command_ms"], "chromium_sandbox": True}
        if executable:
            options["executable_path"] = executable
        else:
            options["channel"] = "chrome"
        browser = playwright.chromium.launch(**options)
        context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                      locale="en-US", timezone_id="UTC", service_workers="block")
        context.set_default_timeout(LIMITS["command_ms"])
        context.set_default_navigation_timeout(LIMITS["command_ms"])
        allowed = set(site["allowed_hosts"])

        def route_request(route):
            url = route.request.url
            parsed = urlparse(url)
            if parsed.scheme in ("about", "data", "blob") or parsed.hostname in allowed:
                route.continue_()
            else:
                recorder.emit("external_request_blocked", url=url)
                route.abort("blockedbyclient")

        context.route("**/*", route_request)
        # Per-step screenshots are masked; trace keeps DOM/actions/network without
        # an unmaskable browser screencast containing accidental visible secrets.
        context.tracing.start(screenshots=False, snapshots=True, sources=True)
        page = context.new_page()
        network = []
        for name in os.environ.get("HARNESS_REDACT_ENV_NAMES", "").split(","):
            if name.strip() and len(os.environ.get(name.strip(), "")) >= 4:
                KNOWN_SECRETS.add(os.environ[name.strip()])
        page.on("request", remember_request)
        page.on("response", lambda response: capture_response(response, network, recorder))
        page.on("pageerror", lambda error: recorder.emit("page_error", error=str(error)))
        page.on("dialog", lambda dialog: (recorder.emit("dialog", type=dialog.type, message=dialog.message), dialog.dismiss()))
        recorder.emit("browser_ready", version=browser.version, transport="native-playwright",
                      fresh_context=True, viewport={"width": 1440, "height": 1000}, sandbox=True)
        result["browser_version"] = browser.version
        phase = "execution"
        harness = ScriptHarness(page, case, plan, adapter, case_out, recorder, network, site["base_url"])
        script = module_from(out / "inputs/scripts.py")
        remember_secrets(case["parameters"])
        invoke_script(script, case, harness)
        require(harness._next == len(case["steps"]), "implementation: script omitted planned steps")
        require(all_steps_matched(case, harness.results), "unconfirmed: script caught a failed step")
        result["status"] = "completed"
    except BaseException as exc:
        from .runner import error_category
        result.update(status="blocked" if phase in ("setup", "browser_start") else
                      (str(exc).split(":")[0] if isinstance(exc, StepMismatch) else "error"),
                      error=str(exc), category="infrastructure" if phase in ("setup", "browser_start") else
                      ("unconfirmed" if isinstance(exc, StepMismatch) else error_category(exc)),
                      traceback=traceback.format_exc(), phase=phase)
        recorder.emit("case_error", error=str(exc), category=result["category"], phase=phase)
    finally:
        if harness:
            result["steps"] = harness.results
            try:
                final = harness._observe()
                final["history"] = harness.history
                write_json(case_out / "final.json", final)
                harness._capture("final")
                checks = adapter.evaluate(canonical_cases([case])[0], harness.initial, final)
                require(isinstance(checks, list) and checks, "independent evaluator returned no checks")
                require(all(isinstance(c.get("id"), str) and type(c.get("passed")) is bool for c in checks), "invalid independent checks")
                result["independent_checks"] = checks
                result["passed"] = (result["status"] == "completed" and all_steps_matched(case, harness.results)
                                    and not final.get("observation_errors") and all(c["passed"] for c in checks))
                if result["status"] == "completed" and not result["passed"]:
                    result["status"] = "independent_failure"
                recorder.emit("independent_evaluation", checks=checks, passed=result["passed"])
            except Exception as exc:
                result.update(passed=False, status="unconfirmed", evaluation_error=str(exc))
        attempted = {s["id"] for s in result["steps"]}
        result["steps"].extend({"id": step["id"], "status": "not_run"} for step in case["steps"] if step["id"] not in attempted)
        if context:
            try:
                context.tracing.stop(path=str(raw_trace))
                sanitize_trace(raw_trace, case_out / "trace.zip")
                result["trace"] = "trace.zip"
            except Exception as exc:
                result.update(passed=False, trace_error=str(exc), status="unconfirmed")
            finally:
                if raw_trace.is_file():
                    raw_trace.unlink()
        for obj in (context, browser):
            if obj:
                try:
                    obj.close()
                except Exception as exc:
                    result.update(passed=False, status="unconfirmed", cleanup_error=str(exc))
        if playwright:
            try:
                playwright.stop()
            except Exception as exc:
                result.update(passed=False, status="unconfirmed", driver_cleanup_error=str(exc))
        result["elapsed_seconds"] = time.monotonic() - start
        recorder.emit("case_complete", result=result)
        recorder.close()
        write_json(case_out / "result.json", result)
    return result


def frozen_files(site, model_dir):
    paths = set(Path(__file__).parent.glob("*.py"))
    # Freeze target adapter dependencies too, without reading model answers.
    adapter_dir = local_path(ROOT, site["adapter"]).parent
    paths.update(adapter_dir.glob("*.py"))
    paths.update(p for p in model_dir.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for entry in site["source_roots"]:
        source = local_path(ROOT, entry)
        paths.update([source] if source.is_file() else
                     (p for p in source.rglob("*") if p.is_file() and "__pycache__" not in p.parts))
    return {str(p.resolve()): digest(p) for p in sorted(paths)}


def stop_owned_tree(child):
    if child.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    else:
        import signal
        os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


def render_report(summary, out):
    rows = []
    for index, case in enumerate(summary["cases"]):
        link = f"cases/{index + 1:02d}-{case['id']}/supervisor-result.json"
        task_link = f"task-{case['id']}.html"
        rows.append(f"<tr><td><a href='{html.escape(task_link)}'>{html.escape(case['id'])}</a> "
                    f"(<a href='{html.escape(link)}'>原始结果</a>)</td>"
                    f"<td>{html.escape(case['status'])}</td><td>{sum(s['status']=='matched' for s in case['steps'])}"
                    f"/{len(case['steps'])}</td><td>{case.get('elapsed_seconds', 0):.2f}s</td>"
                    f"<td>{html.escape(case.get('error', ''))}</td></tr>")
    document = """<!doctype html><html lang="zh"><meta charset="utf-8"><title>阶段一真实浏览器记录</title>
<style>body{font:16px system-ui;max-width:1200px;margin:40px auto;padding:0 20px;color:#17202a}
table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #ddd;text-align:left}
pre{white-space:pre-wrap;background:#f4f6f7;padding:20px}a{color:#1565c0}</style>
<h1>阶段一 · 直接 Playwright 白盒验证</h1>"""
    document += f"<p>运行：{html.escape(summary['run_id'])}；模型作者：gpt-6.1-sol；版本：{html.escape(summary['revision'])}</p>"
    document += "<p>固定分母保留全部失败、拒绝、无法确认与超时。当前为开发/回归结果，不是泛化或速度对照成绩。</p>"
    document += "<p><a href='inputs/model/rulebook.md'>冻结规则书</a> · <a href='inputs/scripts.py'>原生脚本</a> · "
    document += "<a href='inputs/plan.json'>动作前预测</a> · <a href='registration.json'>运行前冻结</a></p>"
    document += "<pre>" + html.escape(json.dumps(summary["metrics"], ensure_ascii=False, indent=2)) + "</pre>"
    document += "<table><tr><th>任务</th><th>状态</th><th>匹配步骤</th><th>用时</th><th>失败原因</th></tr>" + "".join(rows) + "</table>"
    (out / "report.html").write_text(document + "</html>", encoding="utf-8")


def execute(site_path, model_dir, out, protocol, case_seconds=180, baseline_summary=None):
    require(0 < case_seconds <= LIMITS["case_seconds"], "invalid or expanded registered timeout")
    site_path, model_dir, out, protocol = map(lambda p: Path(p).resolve(), (site_path, model_dir, out, protocol))
    site = read_json(site_path)
    cases = read_json(local_path(ROOT, site["cases"]))
    plan, rules = read_json(model_dir / "plan.json"), read_json(model_dir / "rules.json")
    counts = validate_inputs(site, cases, rules, plan)
    baseline = read_json(baseline_summary) if baseline_summary else None
    if baseline:
        from .handoff import validate_repair
        baseline_dir = Path(baseline_summary).resolve().parent
        parent = read_json(baseline_dir / "inputs/plan.json")
        parent["rules"] = read_json(baseline_dir / "inputs/rules.json")
        candidate = {**plan, "rules": rules}
        require(baseline.get("repair_round", 0) < 2, "maximum two model repair rounds")
        validate_repair(parent, candidate, read_json(model_dir / "diagnosis.json"))
    out.mkdir(parents=True, exist_ok=False)
    inputs = out / "inputs"
    inputs.mkdir()
    (out / "cases").mkdir()
    for source, name in ((site_path, "site.json"), (model_dir / "plan.json", "plan.json"),
                         (model_dir / "rules.json", "rules.json"), (model_dir / "scripts.py", "scripts.py"),
                         (protocol, "PROTOCOL.md")):
        shutil.copyfile(source, inputs / name)
    write_json(inputs / "cases.json", cases)
    shutil.copytree(model_dir, inputs / "model", ignore=shutil.ignore_patterns("__pycache__"))
    hashes = frozen_files(site, model_dir)
    from .artifacts import source_manifest
    source_hashes = source_manifest(site, ROOT)
    if baseline:
        require(baseline["source_hashes"] == source_hashes, "website/evaluator changed across model repair")
    freeze = {"run_id": out.name, "phase": "phase1_development_or_regression", "revision": plan["revision"],
              "model": plan["model"], "source_and_implementation_hashes": hashes, "counts": counts,
              "input_hashes": {p.relative_to(inputs).as_posix(): digest(p) for p in inputs.rglob("*") if p.is_file()},
              "limits": {**LIMITS, "case_seconds": case_seconds}, "argv": sys.argv,
              "registered_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "runtime": {"python": sys.version, "platform": platform.platform()},
              "model_tokens": None, "model_cost": None}
    write_json(out / "registration.json", freeze)
    # Snapshot code to support reviewing old runs after infrastructure revisions.
    for name in hashes:
        path = Path(name)
        if path.is_relative_to(ROOT):
            destination = out / "frozen" / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    started = time.monotonic()
    results = []
    for index, case in enumerate(plan["cases"]):
        case_out = out / "cases" / f"{index + 1:02d}-{case['id']}"
        remaining = LIMITS["run_seconds"] - (time.monotonic() - started)
        if remaining <= 0:
            result = {"id": case["id"], "status": "not_run", "passed": False, "error": "overall budget exhausted",
                      "steps": [{"id": s["id"], "status": "not_run"} for s in case["steps"]]}
        else:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            gate = out / f"worker-{index + 1:02d}.start"
            timed_out, cleanup_error, ownership_error = False, None, None
            with (out / f"worker-{index + 1:02d}.log").open("xb") as log:
                child = subprocess.Popen([sys.executable, "-m", "harness.playwright_run", "--worker",
                                          "--out", str(out), "--index", str(index), "--start-gate", str(gate)], cwd=ROOT,
                                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                         creationflags=flags, start_new_session=os.name != "nt")
                group = None
                try:
                    from .process_group import OwnedProcessGroup
                    group = OwnedProcessGroup(child)
                    # Worker cannot launch browser descendants until ownership is established.
                    gate.write_text("owned", encoding="ascii")
                    child.wait(timeout=min(case_seconds, remaining))
                except subprocess.TimeoutExpired:
                    timed_out = True
                except Exception as exc:
                    ownership_error = str(exc)
                finally:
                    try:
                        if group:
                            group.close()
                        elif child.poll() is None:
                            child.terminate()  # gated worker has not launched any children
                            child.wait(timeout=10)
                    except Exception as exc:
                        cleanup_error = str(exc)
                        try:
                            stop_owned_tree(child)
                        except Exception as fallback_error:
                            cleanup_error += "; " + str(fallback_error)
            if (case_out / "result.json").is_file():
                result = read_json(case_out / "result.json")
            else:
                events = []
                if (case_out / "events.jsonl").is_file():
                    for line in (case_out / "events.jsonl").read_text(encoding="utf-8").splitlines():
                        try:
                            events.append(json.loads(line))
                        except ValueError:
                            pass
                steps = {e["step"]: e["result"] for e in events if e.get("kind") == "step_result"}
                result = {"id": case["id"], "status": "timeout_or_worker_failure", "passed": False,
                          "error": "owned worker exited without final result", "worker_exit_code": child.returncode,
                          "steps": [steps.get(s["id"], {"id": s["id"], "status": "not_run"}) for s in case["steps"]]}
            if timed_out:
                result.update(passed=False, status="timeout", timeout_seconds=min(case_seconds, remaining))
            if cleanup_error or ownership_error:
                result.update(passed=False, status="infrastructure_failure",
                              cleanup_error=cleanup_error, ownership_error=ownership_error)
        case_out.mkdir(parents=True, exist_ok=True)
        write_json(case_out / "supervisor-result.json", result)
        results.append(result)
        print(json.dumps({"case": case["id"], "status": result["status"], "passed": result["passed"],
                          "matched": sum(s["status"] == "matched" for s in result["steps"]),
                          "planned": len(case["steps"])}, ensure_ascii=False), flush=True)
    changes = [name for name, expected in hashes.items() if not Path(name).is_file() or digest(name) != expected]
    changes.extend("inputs/" + name for name, expected in freeze["input_hashes"].items()
                   if not (inputs / name).is_file() or digest(inputs / name) != expected)
    if changes:
        for result in results:
            result["passed"] = False
        write_json(out / "integrity-errors.json", changes)
    matched = sum(s["status"] == "matched" for c in results for s in c["steps"])
    dispatched = sum(s["status"] != "not_run" for c in results for s in c["steps"])
    completed = sum(bool(s.get("action_completed")) for c in results for s in c["steps"])
    regressions = []
    if baseline:
        previous = {c["id"]: c for c in baseline["cases"]}
        for case in results:
            old = previous[case["id"]]
            if old["passed"] and not case["passed"]:
                regressions.append(case["id"])
            old_steps = {s["id"]: s for s in old["steps"]}
            for step in case["steps"]:
                if old_steps.get(step["id"], {}).get("status") == "matched" and step["status"] != "matched":
                    regressions.append(case["id"] + "/" + step["id"])
    summary = {"run_id": out.name, "site_id": site["site_id"], "revision": plan["revision"],
               "source_hashes": source_hashes, "fixed_cases": canonical_cases(cases),
               "repair_round": baseline.get("repair_round", 0) + 1 if baseline else 0,
               "baseline_summary": str(baseline_summary) if baseline_summary else None,
               "regressions": regressions,
               "cases": results, "integrity_errors": changes, "model_tokens": None, "model_cost": None,
               "measurement_status": "not_started" if not dispatched else "completed" if completed == counts["steps"] else "partial",
               "metrics": {"case_denominator": len(cases), "passed_cases": sum(c["passed"] for c in results),
                           "step_denominator": counts["steps"], "matched_steps": matched,
                           "ui_actions_dispatched": dispatched, "ui_actions_completed": completed,
                           "case_success_rate": sum(c["passed"] for c in results) / len(cases) if dispatched else None,
                           "step_match_rate": matched / counts["steps"] if dispatched else None,
                           "elapsed_seconds": time.monotonic() - started},
               "activation_allowed": not changes and not regressions and all(c["passed"] for c in results)}
    write_json(out / "summary.json", summary)
    write_json(out / "feedback.json", {"revision": plan["revision"],
               "failures": [c for c in results if not c["passed"]], "integrity_errors": changes})
    render_report(summary, out)
    from .present import render
    render(out)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site")
    parser.add_argument("--model-dir")
    parser.add_argument("--protocol")
    parser.add_argument("--out", required=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--index", type=int)
    parser.add_argument("--start-gate")
    parser.add_argument("--baseline-summary")
    args = parser.parse_args()
    if args.worker:
        if args.start_gate:
            deadline = time.monotonic() + 20
            while not Path(args.start_gate).exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("infrastructure: supervisor did not establish worker ownership")
                time.sleep(0.05)
        return 0 if run_worker(Path(args.out), args.index)["passed"] else 1
    result = execute(args.site, args.model_dir, args.out, args.protocol, baseline_summary=args.baseline_summary)
    print(json.dumps(result["metrics"], ensure_ascii=False))
    return 0 if result["activation_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
