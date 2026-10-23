"""Linux transport for independent exact-Solar browser-only sessions.

Only this trusted management module sees private launch paths. Learner shell
commands use the named root-deny Codex namespace; only the MCP broker receives
the fixed-origin Unix socket. No model call occurs during prepare/preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

RUNTIME = Path(__file__).resolve().parent / "runtime"
CODEX = "/opt/codex/bin/codex"
PYTHON = "/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python"
MODEL = "gpt-6.1-sol"


def resolve_runtime_source(value=None):
    """Resolve only coordinator-owned generic runtime trees, never job input."""
    source = Path(RUNTIME if value is None else value).resolve()
    default = Path(__file__).resolve().parent / "runtime"
    if source != default:
        source.relative_to(default.parent / "runtime_versions")
    if not source.is_dir() or any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("trusted generic runtime source must be a directory without symlinks")
    return source


def _module(name, *, runtime_source=None):
    source = resolve_runtime_source(runtime_source)
    spec = importlib.util.spec_from_file_location("replica_" + name, source / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def make_socket_path():
    """Short private Unix pathname, independent of long evidence/run IDs."""
    directory = Path(__file__).resolve().parents[2] / "work" / "replica-sockets"
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    return directory / (uuid.uuid4().hex[:20] + ".sock")


def prepare_session(config: dict) -> dict:
    """Create immutable launch files, without contacting a model.

    Required config: run_dir, origin, prompt. Optional fixture is public only.
    run_dir must be a new directory; model-visible files live under workspace/,
    management-only configs/state/logs under private/.
    """
    from urllib.parse import urlsplit
    origin = config["origin"].rstrip("/")
    target = urlsplit(origin)
    if target.scheme != "http" or not target.hostname or target.path or target.query or target.fragment or target.username:
        raise ValueError("one plain HTTP origin is required")
    root = Path(config["run_dir"]).resolve()
    root.mkdir(parents=True, exist_ok=False)
    workspace, private = root / "workspace", root / "private"
    workspace.mkdir(mode=0o700)
    private.mkdir(mode=0o700)
    # Freeze only generic code. No repository/target source or historical files.
    runtime = private / "runtime"
    runtime_source = resolve_runtime_source(config.get("runtime_source"))
    shutil.copytree(runtime_source, runtime, ignore=shutil.ignore_patterns("__pycache__"))
    # Versioned sources carry their own normalizer. The development runtime
    # obtains it from the shared implementation when it has no local copy.
    if not (runtime / "trees.py").exists():
        shutil.copyfile(Path(__file__).resolve().parent / "trees.py", runtime / "trees.py")
    # Only observational runtime modules are exposed to learner commands.
    public_runtime = root / "generic-runtime"
    public_runtime.mkdir(mode=0o700)
    for name in ("script_policy.py", "observation.py", "BROWSER_INTERFACE.md"):
        shutil.copyfile(runtime / name, public_runtime / name)
    runtime_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.glob("*.py")}
    runtime_file_hashes = {str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(runtime.rglob("*")) if p.is_file()}
    runtime_source_file_hashes = {str(p.relative_to(runtime_source)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(runtime_source.rglob("*"))
                                  if p.is_file() and "__pycache__" not in p.relative_to(runtime_source).parts}
    home = private / "codex-home"
    home.mkdir(mode=0o700)
    auth = Path(config.get("auth_source", "/run/codex-environment/codex-home/auth.json")).resolve()
    if not auth.is_file():
        raise FileNotFoundError("existing ChatGPT authentication selector unavailable")
    (home / "auth.json").symlink_to(auth)
    socket_path = make_socket_path()
    broker = {"workspace": str(workspace), "private": str(private / "broker"),
              "runtime": str(runtime), "origin": origin, "socket": str(socket_path),
              "fixture_path": str(private / "public-fixture.json"),
              "action_limit": int(config.get("action_limit", 120)),
              "script_call_limit": int(config.get("script_call_limit", 30)),
              "time_limit_seconds": int(config.get("time_limit_seconds", 1800))}
    _write(private / "public-fixture.json", config.get("fixture", {}))
    _write(private / "broker-config.json", broker)
    (private / "prompt.txt").write_text(config["prompt"], encoding="utf-8")
    plan = {"model": MODEL, "fresh_context": True, "run_dir": str(root),
            "workspace": str(workspace), "private": str(private),
            "runtime": str(runtime), "public_runtime": str(public_runtime),
            "codex_home": str(home), "auth_source": str(auth),
            "prompt_path": str(private / "prompt.txt"),
            "broker_config": str(private / "broker-config.json"), "origin": origin,
            "socket": str(socket_path), "upstream_host": config.get("upstream_host", target.hostname),
            "upstream_port": int(config.get("upstream_port", target.port or 80)),
            "time_limit_seconds": broker["time_limit_seconds"],
            "reasoning_effort": config.get("reasoning_effort", "high"),
            "runtime_source":str(runtime_source), "runtime_hashes": runtime_hashes,
            "runtime_file_hashes":runtime_file_hashes, "runtime_source_file_hashes":runtime_source_file_hashes,
            "public_fixture": config.get("fixture", {}),
            "init_script": config.get("init_script")}
    _write(private / "launch-plan.json", plan)
    return plan


def build_command(plan: dict) -> list[str]:
    permissions = _module("permissions")
    args = [CODEX, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--strict-config", "--skip-git-repo-check", "-m", MODEL,
            "-C", plan["workspace"], "--json", "-o", str(Path(plan["private"]) / "last-message.txt")]
    args += permissions.overrides(extra_paths={plan["public_runtime"]: "read"})
    args += ["-c", "model_reasoning_effort=" + permissions.toml_inline(plan["reasoning_effort"])]
    args += ["-c", "mcp_servers.browser=" + permissions.toml_inline({
        "command": PYTHON,
        "args": [str(Path(plan["runtime"]) / "browser_broker.py"), "--config", plan["broker_config"]],
        "enabled": True, "startup_timeout_sec": 30, "tool_timeout_sec": 330,
        "tools": {"execute_script": {"approval_mode": "approve"}, "status": {"approval_mode": "approve"}},
    })]
    return args + ["-"]


class OriginGateway:
    """Trusted management gateway, reachable only by browser worker namespaces."""
    def __init__(self, plan):
        self.plan = plan
        self.server = _module("unix_gateway").make_gateway(
            plan["socket"], plan["origin"], plan["upstream_host"], plan["upstream_port"])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    def __enter__(self):
        self.thread.start()
        return self
    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        Path(self.plan["socket"]).unlink(missing_ok=True)


def build_browser_command(plan: dict, job_path, *, state_dir=None, step_barrier_dir=None):
    """Build isolated browser command; job exports def run(h), never model CLI."""
    return _module("worker_sandbox").command(plan["runtime"], job_path, plan["socket"],
        state_dir=state_dir, step_barrier_dir=step_barrier_dir)



def launch_diagnostic(plan: dict, exit_code=None) -> dict:
    """Classify transport logs without retrying or contacting a model."""
    private = Path(plan["private"])
    values = []
    for name in ("stderr.txt", "events.jsonl"):
        path = private / name
        if path.exists():
            values.append(path.read_text(encoding="utf-8", errors="replace"))
    content = "\n".join(values).lower()
    category = None
    if "403" in content and ("connect" in content or "proxy" in content):
        category = "remote_authorization/network_block"
    elif "401" in content or "unauthorized" in content:
        category = "remote_authorization"
    elif exit_code not in (None, 0):
        category = "cli_failure_unclassified"
    journal = private / "broker" / "broker.jsonl"
    return {"failure_category": category, "broker_journal_present": journal.exists(),
            "retry_performed": False, "credentials_modified": False,
            "usage_or_cost_inferred": False}


def launch_session(plan: dict, *, allow_model_call: bool = False) -> dict:
    """Run a paid independent learner only after management explicitly enables it."""
    if not allow_model_call:
        raise PermissionError("model calls disabled: pass allow_model_call=True after coordinator authorization")
    if plan.get("model") != MODEL or not plan.get("fresh_context"):
        raise ValueError("independent exact gpt-6.1-sol context required")
    private = Path(plan["private"])
    args = build_command(plan)
    env = dict(os.environ)
    env.update({"HOME": str(private / "isolated-home"),
                "CODEX_HOME": plan["codex_home"], "LANG": "C.UTF-8",
                "PYTHONNOUSERSITE": "1"})
    Path(env["HOME"]).mkdir(mode=0o700, exist_ok=True)
    nonce = uuid.uuid4().hex
    receipt = private / ("cleanup-" + nonce + ".json")
    command = [PYTHON, str(Path(plan["runtime"]) / "process_guard.py"),
               "--receipt", str(receipt), "--nonce", nonce, "--", *args]
    started = time.monotonic()
    timeout = False
    with OriginGateway(plan), (private / "events.jsonl").open("xb") as out, (private / "stderr.txt").open("xb") as err:
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=out, stderr=err, env=env, start_new_session=True)
        child.stdin.write(Path(plan["prompt_path"]).read_bytes())
        child.stdin.close()
        try:
            code = child.wait(timeout=plan["time_limit_seconds"])
        except subprocess.TimeoutExpired:
            timeout = True
            os.killpg(child.pid, signal.SIGTERM)
            try:
                code = child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                code = child.wait(timeout=20)
    usage = []
    for line in (private / "events.jsonl").read_text().splitlines():
        try:
            event = json.loads(line)
            if "usage" in event:
                usage.append(event["usage"])
        except ValueError:
            pass
    clean = _module("process_guard").receipt_valid(receipt, nonce=nonce, supervisor_pid=child.pid)
    result = {"model": MODEL, "fresh_context": True, "launch_channel": "standalone_codex_cli_child",
              "exit_code": code, "timeout": timeout, "elapsed_seconds": time.monotonic() - started,
              "process_tree_clean": clean, "cleanup_receipt": str(receipt), "cleanup_nonce": nonce,
              "supervisor_pid": child.pid, "usage_events": usage, "cost": None, "command": args,
              "transport_diagnostic": launch_diagnostic(plan, code)}
    _write(private / "launch-result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--config", required=True)
    launch = sub.add_parser("launch")
    launch.add_argument("--plan", required=True)
    launch.add_argument("--allow-model-call", action="store_true")
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare_session(json.loads(Path(args.config).read_text()))
    else:
        result = launch_session(json.loads(Path(args.plan).read_text()), allow_model_call=args.allow_model_call)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
