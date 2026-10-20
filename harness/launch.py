"""Prepare, supervise, validate, and run one trusted local site configuration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .artifacts import digest, freeze, verify_frozen, write_json
from .contract import load_inputs, local_path, repository_root, require
from .preflight import execute as preflight, local_http, probe_http
from .runner import execute as run_experiment


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def command_argv(site, key):
    """Commands belong to the trusted deployment adapter, never the model bundle."""
    value = site.get(key)
    require(isinstance(value, list) and value and
            all(isinstance(item, str) and item and "\0" not in item for item in value),
            f"trusted site configuration requires a nonempty {key} argument array")
    command = list(value)
    if command[0].lower() in ("python", "python3", "python.exe"):
        command[0] = sys.executable
    return command


def spawn(command, cwd, log_path, environment):
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    with Path(log_path).open("xb") as output:
        return subprocess.Popen(command, cwd=cwd, env=environment,
                                stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, shell=False, **options)


def stop_owned(process, stop_file=None, grace_seconds=15):
    """Ask our launcher to unwind; forced cleanup is limited to its own tree."""
    if process is None or process.poll() is not None:
        return {"status": "already_stopped"}
    if stop_file is not None:
        Path(stop_file).write_text("stop requested by owning Harness\n", encoding="utf-8")
        try:
            process.wait(timeout=grace_seconds)
            return {"status": "cooperative", "returncode": process.returncode}
        except subprocess.TimeoutExpired:
            pass
    if os.name == "nt":
        # shell=False; this PID is the Popen child we still own, not a port lookup.
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
        killed = subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=15,
                                shell=False, creationflags=subprocess.CREATE_NO_WINDOW)
        if killed.returncode and process.poll() is None:
            raise RuntimeError(f"owned process cleanup failed: pid={process.pid}")
    else:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)
    return {"status": "forced_owned_tree", "returncode": process.returncode}


def wait_ready(process, urls, timeout):
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"site launcher exited with code {process.returncode}; inspect site.log")
        last = {url: probe_http(url) for url in urls}
        if all(value.get("available") for value in last.values()):
            return last
        time.sleep(0.5)
    raise TimeoutError(f"site readiness exceeded {timeout}s: {last}")


def check_integrity(out, root, site):
    """A missing/changed source is evidence of failure, not a reason to lose reports."""
    try:
        return verify_frozen(out, root, site)
    except Exception as exc:
        return [f"integrity verification unavailable: {exc}"]


def recover_execution(out, state, expected_steps):
    """Recover measurement evidence after an interrupted runner without inventing success."""
    directory = out / "execution"
    summary_path = directory / "summary.json"
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            state.update(measurement_status=summary["measurement_status"],
                         case_success_rate=summary["metrics"]["case_success_rate"],
                         step_match_rate=summary["metrics"]["step_match_rate"],
                         execution_summary="execution/summary.json")
            return
        except Exception as exc:
            state["execution_summary_error"] = str(exc)
    events = directory / "events.jsonl"
    if not events.is_file():
        return
    dispatched = completed = 0
    malformed = 0
    for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise TypeError("event must be object")
            kind = event.get("kind")
        except (ValueError, TypeError):
            malformed += 1
            continue
        dispatched += kind == "action_dispatch"
        completed += kind == "action_complete"
    dispatched = max(dispatched, completed)
    state.update(ui_actions_dispatched=dispatched, ui_actions_completed=completed,
                 measurement_status="not_started" if dispatched == 0 else
                 "completed" if completed == expected_steps else "partial",
                 recovered_execution_evidence="execution/events.jsonl",
                 measurement_recovery_note="Action events recover measurement progress only; missing final metrics remain unknown.")
    if malformed:
        state["malformed_event_lines"] = malformed


def execute(site_path, bundle_path, out, *, skip_setup=False, cdp_url=None,
            baseline_summary=None, diagnosis_path=None, setup_timeout=1800, startup_timeout=120):
    root = repository_root().resolve()
    site_path, bundle_path, out = (Path(value).resolve() for value in (site_path, bundle_path, out))
    for label, path in (("site", site_path), ("bundle", bundle_path), ("out", out)):
        require(path.is_relative_to(root), f"{label} path escapes workspace: {path}")
    # Validate all command inputs before running any trusted deployment code.
    site, bundle, cases = load_inputs(site_path, bundle_path, root)
    start_command = command_argv(site, "start_argv")
    setup_command = None if skip_setup else command_argv(site, "setup_argv")
    working_directory = local_path(root, site.get("working_directory", "."))
    urls = site.get("health_urls", [site["base_url"]])
    require(isinstance(urls, list) and urls, "health_urls must be a nonempty list")
    for url in urls:
        local_http(url)
    if cdp_url:
        local_http(cdp_url)
    require(setup_timeout > 0 and startup_timeout > 0, "timeouts must be positive")
    out.mkdir(parents=True, exist_ok=False)
    frozen = freeze(site_path, bundle_path, site, cases, out, root)
    fixed_cases_path = local_path(root, site["cases"]) if "cases" in site else site_path.with_name("cases.json")
    original_inputs = {path: digest(path) for path in (site_path, bundle_path, fixed_cases_path)}
    stop_file = out / "stop-service"
    environment = {**os.environ, "PYTHONUNBUFFERED": "1", "HARNESS_STOP_FILE": str(stop_file)}
    state = {
        "kind": "supervised_experiment_launch", "site_id": site["site_id"],
        "revision": bundle["revision"], "status": "starting", "stage": "initialization",
        "measurement_status": "not_started", "started_utc": utc_now(),
        "case_success_rate": None, "step_match_rate": None, "model_called": False,
        "setup_argv": setup_command, "start_argv": start_command,
        "setup_skipped": skip_setup, "bundle_sha256": frozen["inputs"]["bundle.json"],
        "original_input_sha256": {path.relative_to(root).as_posix(): value for path, value in original_inputs.items()},
        "permission_environment": {key: os.environ.get(key) for key in
                                   ("CODEX_PERMISSION_PROFILE", "CODEX_SANDBOX_NETWORK_DISABLED")},
        "timing_note": "Setup and startup durations are separate from target UI execution metrics.",
    }
    processes = []
    started = time.monotonic()

    def integrity():
        errors = check_integrity(out, root, site)
        for path, expected in original_inputs.items():
            try:
                if digest(path) != expected:
                    errors.append(f"original launch input changed: {path.relative_to(root).as_posix()}")
            except Exception as exc:
                errors.append(f"original launch input unavailable: {path.relative_to(root).as_posix()}: {exc}")
        return errors

    def save(stage=None):
        if stage:
            state["stage"] = stage
            print(f"Harness: {stage}", flush=True)
        write_json(out / "launch.json", state)

    try:
        save()
        if setup_command:
            save("setup")
            phase_started = time.monotonic()
            process = spawn(setup_command, working_directory, out / "setup.log", environment)
            processes.append((process, None))
            code = process.wait(timeout=setup_timeout)
            state["setup_seconds"] = time.monotonic() - phase_started
            require(code == 0, f"setup failed with code {code}; inspect setup.log")
        state["integrity_errors"] = integrity()
        require(not state["integrity_errors"], "source or input changed during setup")
        save("site_startup")
        phase_started = time.monotonic()
        process = spawn(start_command, working_directory, out / "site.log", environment)
        processes.append((process, stop_file))
        state["site_launcher_pid"] = process.pid
        state["site_health"] = wait_ready(process, urls, startup_timeout)
        state["startup_seconds"] = time.monotonic() - phase_started
        state["integrity_errors"] = integrity()
        require(not state["integrity_errors"], "source or input changed during site startup")
        save("browser_preflight")
        ready = preflight(site_path, bundle_path, out / "preflight",
                          cdp_url=cdp_url, launch_browser=cdp_url is None, smoke=True)
        state["preflight"] = "preflight/preflight.json"
        require(ready["ready_for_measurement"], "environment/browser preflight failed; inspect preflight/report.html")
        state["integrity_errors"] = integrity()
        require(not state["integrity_errors"], "source or input changed during preflight")
        save("execution")
        summary = run_experiment(site_path, bundle_path, out / "execution", cdp_url=cdp_url,
                                 baseline_summary=baseline_summary, diagnosis_path=diagnosis_path)
        state.update(measurement_status=summary["measurement_status"],
                     case_success_rate=summary["metrics"]["case_success_rate"],
                     step_match_rate=summary["metrics"]["step_match_rate"],
                     execution_report="execution/report.html", execution_summary="execution/summary.json")
        state["status"] = "passed" if (summary["measurement_status"] == "completed" and
                                         summary["activation"]["activation_allowed"] and
                                         summary["metrics"].get("passed_cases") == len(cases)) else "failed"
    except (Exception, KeyboardInterrupt) as exc:
        state.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "blocked_or_failed",
                     error=str(exc) or type(exc).__name__, failure_stage=state["stage"])
    finally:
        try:
            recover_execution(out, state, sum(len(case["steps"]) for case in bundle["cases"]))
        except Exception as exc:
            state["measurement_recovery_error"] = str(exc)
        state["cleanup"] = []
        for process, stop in reversed(processes):
            try:
                state["cleanup"].append({"pid": process.pid, **stop_owned(process, stop)})
            except Exception as exc:
                state["cleanup"].append({"pid": process.pid, "status": "failed", "error": str(exc)})
                state["status"] = "cleanup_failed"
        state["integrity_errors"] = integrity()
        if state["integrity_errors"]:
            state["status"] = "integrity_failure"
        state.update(ended_utc=utc_now(), total_lifecycle_seconds=time.monotonic() - started)
        save()
        links = "".join(f'<p><a href="{path}">{label}</a></p>' for path, label in (
            ("preflight/report.html", "环境与浏览器验收"), ("execution/report.html", "目标网站实验结果"))
                        if (out / path).is_file())
        report = ('<!doctype html><meta charset="utf-8"><title>Harness launch</title>'
                  '<style>body{font:16px system-ui;max-width:1000px;margin:40px auto}pre{white-space:pre-wrap}</style>'
                  '<h1>Harness 运行记录</h1><p>状态：' + html.escape(state["status"]) +
                  '</p><p>目标网站测量：' + html.escape(state["measurement_status"]) +
                  '</p>' + links + '<pre>' + html.escape(json.dumps(state, ensure_ascii=False, indent=2)) + '</pre>')
        (out / "report.html").write_text(report, encoding="utf-8")
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--skip-setup", action="store_true", help="Reuse already installed dependencies and frozen fixture.")
    parser.add_argument("--cdp", help="Use a dedicated local Chrome; otherwise launch isolated Chrome.")
    parser.add_argument("--baseline-summary")
    parser.add_argument("--diagnosis")
    parser.add_argument("--setup-timeout", type=float, default=1800)
    parser.add_argument("--startup-timeout", type=float, default=120)
    args = parser.parse_args(argv)
    try:
        state = execute(args.site, args.bundle, args.out, skip_setup=args.skip_setup, cdp_url=args.cdp,
                        baseline_summary=args.baseline_summary, diagnosis_path=args.diagnosis,
                        setup_timeout=args.setup_timeout, startup_timeout=args.startup_timeout)
        print(json.dumps({"status": state["status"], "measurement_status": state["measurement_status"],
                          "report": str(Path(args.out).resolve() / "report.html")}, ensure_ascii=False, indent=2))
        return 0 if state["status"] == "passed" else 1
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
