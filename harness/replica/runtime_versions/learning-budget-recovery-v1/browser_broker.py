"""A stdio MCP server owned by the coordinator, outside learner tool namespaces.

It accepts native Playwright scripts, validates the observation interface, runs
each in another restricted Linux namespace, and exports only public evidence.
Website source, evaluators, database and management controls are never mounted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from process_guard import receipt_valid
from permissions import CODEX, CORE, overrides
from script_policy import validate_script, UnsupportedInterface
from worker_sandbox import command as worker_command
from budget_ledger import recover as recover_budget, action_evidence


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.flush()
        os.fsync(out.fileno())


def relative_file(root, value):
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("workspace-relative file required")
    result = (root / candidate).resolve()
    result.relative_to(root.resolve())
    if not result.is_file():
        raise ValueError("input file is missing")
    return result


class Broker:
    def __init__(self, config):
        self.config = config
        self.workspace = Path(config["workspace"])
        self.private = Path(config["private"])
        self.private.mkdir(parents=True, exist_ok=True)
        self.runtime = Path(config["runtime"])
        self.state_dir = self.private / "state"
        self.state_dir.mkdir(exist_ok=True)
        self.state = self.state_dir / "browser-state.json"
        self.journal = self.private / "broker.jsonl"
        recovered = recover_budget(self.private, self.config)
        self.actions, self.calls = recovered["actions"], recovered["calls"]
        self.next_call_number = recovered["next_call_number"]
        self.closed_reason = recovered["closed_reason"]
        self.elapsed_base = recovered["elapsed_seconds"]
        self.started = time.monotonic()
        self.recovery = recovered

    def elapsed(self):
        return self.elapsed_base + time.monotonic() - self.started

    def log(self, value):
        with self.journal.open("a", encoding="utf-8") as out:
            out.write(json.dumps(value, ensure_ascii=False) + "\n")
            out.flush()
            os.fsync(out.fileno())

    def status(self):
        return {"actions": self.actions, "action_limit": self.config["action_limit"],
                "script_calls": self.calls, "script_call_limit": self.config.get("script_call_limit", 40),
                "elapsed_seconds": self.elapsed(), "stop_reason": self.closed_reason,
                "next_call_number": self.next_call_number,
                "budget_recovery":{"counts_complete":self.recovery["counts_complete"],
                                   "errors":self.recovery["errors"]},
                "page_lifecycle": "new_page_about_blank_each_call",
                "persisted_state": ["cookies", "localStorage"], "not_persisted": ["open_pages", "sessionStorage"],
                "navigation_required_each_call": True}

    def close_policy(self, reason):
        self.closed_reason = "policy_rejection:" + str(reason)[:1000]
        self.log({"event": "policy_rejection", "stop_reason": self.closed_reason, "time_ns": time.time_ns()})

    def execute(self, arguments):
        if self.closed_reason:
            raise ValueError("execution stopped: " + self.closed_reason)
        try:
            return self.execute_inner(arguments)
        except (ValueError, SyntaxError, KeyError, TypeError) as error:
            recoverable = isinstance(error, (UnsupportedInterface, SyntaxError))
            self.log({"event":"interface_rejection", "failure_category":"pre_execution_interface" if recoverable else "policy_boundary",
                      "recoverable":recoverable, "error":str(error), "closed":not recoverable})
            if not recoverable and not self.closed_reason:
                self.close_policy(type(error).__name__ + ": " + str(error))
            raise

    def execute_inner(self, arguments):
        if self.closed_reason:
            raise ValueError("execution stopped: " + self.closed_reason)
        if self.calls >= self.config.get("script_call_limit", 40) or self.actions >= self.config["action_limit"]:
            self.closed_reason = "budget_exhausted"
            self.log({"event": "stop", "stop_reason": self.closed_reason})
            raise ValueError("registered execution budget exhausted")
        if self.elapsed() >= self.config["time_limit_seconds"]:
            self.closed_reason = "time_budget_exhausted"
            self.log({"event":"stop", "stop_reason":self.closed_reason})
            raise ValueError("registered time budget exhausted")
        path = relative_file(self.workspace, arguments["script_path"])
        source = path.read_text(encoding="utf-8")
        modules = {}
        for value in arguments.get("modules", []):
            module_path = relative_file(self.workspace, value)
            if not module_path.stem.isidentifier() or module_path.suffix != ".py":
                raise ValueError("module needs a plain Python module filename")
            modules[module_path.stem] = module_path.read_text(encoding="utf-8")
        validate_script(source, module_names=modules)
        for value in modules.values():
            validate_script(value, module_names=modules)
        key = f"call-{self.next_call_number:03d}-{uuid.uuid4().hex[:8]}"
        job_dir = self.private / key
        job_dir.mkdir()
        job = {"origin": self.config["origin"], "socket": self.config["socket"],
               "fixture": json.loads(Path(self.config["fixture_path"]).read_text()),
               "script": source, "modules": modules,
               "state_path": str(self.state), "action_limit": self.config["action_limit"] - self.actions,
               "intent": self.config.get("intent")}
        write_new(job_dir / "job.json", job)
        self.log({"event": "dispatch", "call": key, "script_sha256": hashlib.sha256(source.encode()).hexdigest(),
                  "time_ns": time.time_ns(), "actions_before": self.actions,
                  "calls_before":self.calls, "elapsed_seconds_total":self.elapsed()})
        # A dispatch consumes its call before the worker can start or be killed.
        self.calls += 1
        self.next_call_number += 1
        extra = {str(self.state_dir): "write"}
        if not self.state.exists():
            self.state.write_text('{"cookies": [], "origins": []}')
        args = worker_command(self.runtime, job_dir / "job.json", self.config["socket"], state_dir=self.state_dir)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(job_dir), "TMPDIR": str(job_dir),
               "LANG": "C.UTF-8", "NO_PROXY": "", "no_proxy": ""}
        started = time.monotonic()
        timed_out = False
        cleanup_dir = self.private / "cleanup"
        cleanup_dir.mkdir(mode=0o700, exist_ok=True)
        cleanup_nonce = uuid.uuid4().hex
        cleanup_receipt = cleanup_dir / (cleanup_nonce + ".json")
        with (job_dir / "executor.stdout.txt").open("x") as stdout, (job_dir / "executor.stderr.txt").open("x") as stderr:
            child = subprocess.Popen([sys.executable, str(self.runtime / "process_guard.py"),
                                      "--receipt", str(cleanup_receipt), "--nonce", cleanup_nonce, "--", *args],
                                     env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = child.wait(timeout=min(300, self.config["time_limit_seconds"] - self.elapsed()))
            except subprocess.TimeoutExpired:
                import signal
                timed_out = True
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    code = child.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    code = child.wait(timeout=20)
        tree_clean = receipt_valid(cleanup_receipt, nonce=cleanup_nonce, supervisor_pid=child.pid)
        evidence = job_dir / "evidence"
        result_path = evidence / "result.json"
        if result_path.exists():
            result = json.loads(result_path.read_text())
        else:
            count, _, _ = action_evidence(evidence / "actions.jsonl")
            result = {"status": "error", "actions": count, "error": "executor_timeout" if timed_out else "executor_failure",
                      "diagnostic": (job_dir / "executor.stderr.txt").read_text()[-6000:]}
        if not tree_clean:
            result["status"] = "error"
            result["error"] = "process_tree_cleanup_unconfirmed"
            self.closed_reason = "process_tree_cleanup_unconfirmed"
        journal_count, journal_errors, journal_refusal = action_evidence(evidence / "actions.jsonl")
        self.actions += max(result["actions"], journal_count)
        if journal_refusal and not self.closed_reason:
            self.closed_reason = journal_refusal
        if journal_errors and not self.closed_reason:
            self.closed_reason = "budget_recovery_unconfirmed:action_journal_integrity"
        if timed_out:
            self.closed_reason = "executor_timeout_unconfirmed_effect"
        if result.get("failure_category") == "boundary":
            self.close_policy(result.get("error", "runtime boundary rejection"))
        elif result.get("failure_category") == "runtime_terminated":
            self.closed_reason = "runtime_terminated:" + str(result.get("terminal_reason", "browser unavailable"))
        public = self.workspace / "evidence" / key
        if evidence.exists():
            shutil.copytree(evidence, public)
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence.iterdir() if p.is_file()}
            write_new(job_dir / "public-evidence-hashes.json", hashes)
        outcome = {"call": key, "execution_exit_code": code, "process_tree_clean": tree_clean, "cleanup_receipt": str(cleanup_receipt.relative_to(self.private)),
                   "cleanup_nonce": cleanup_nonce, "supervisor_pid": child.pid, "result": result,
                   "evidence_directory": "evidence/" + key, "budget": self.status()}
        write_new(job_dir / "management-result.json", outcome)
        self.log({"event": "result", "call": key, "actions": result["actions"], "status": result["status"],
                  "elapsed_seconds": time.monotonic() - started, "stop_reason": self.closed_reason,
                  "elapsed_seconds_total":self.elapsed()})
        return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--execute-file")
    args = parser.parse_args()
    broker = Broker(json.loads(Path(args.config).read_text()))
    if args.execute_file:
        print(json.dumps(broker.execute(json.loads(Path(args.execute_file).read_text()))))
        return
    tools = [
        {"name": "execute_script", "description": "Execute your workspace Python script with native Playwright in the isolated browser. EACH CALL starts a NEW browser/Page at about:blank; ONLY cookies/localStorage persist, not open pages or sessionStorage. Every call must explicitly h.expect(...); h.page.goto(h.origin or your known same-origin path). Ordinary locator failures are recoverable in a later call; policy denials close the broker. Export def run(h); h.page is native Page, h.origin and h.fixture are public configuration. Call h.expect(prediction, rationale) before EACH UI action. Use h.observe(label), h.network(), h.note(text) for evidence. Client code, raw HTTP, mutation and runtime internals are excluded. Use normal native locators. Your full result/evidence paths and remaining budget are returned; original evidence is privately preserved.",
         "inputSchema": {"type": "object", "properties": {"script_path": {"type": "string"}, "modules": {"type": "array", "items": {"type": "string"}}}, "required": ["script_path"], "additionalProperties": False}},
        {"name": "status", "description": "Read authoritative experiment interaction and time budget.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    ]
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if "id" not in request:
                continue
            method = request.get("method")
            if method == "initialize":
                result = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
                          "capabilities": {"tools": {}}, "serverInfo": {"name": "replica-native-playwright", "version": "1.0"}}
            elif method == "tools/list":
                result = {"tools": tools}
            elif method == "ping":
                result = {}
            elif method in {"resources/list", "resources/templates/list"}:
                result = {"resources" if method == "resources/list" else "resourceTemplates": []}
            elif method == "tools/call":
                parameters = request["params"]
                try:
                    if parameters["name"] == "execute_script":
                        value = broker.execute(parameters.get("arguments", {}))
                    elif parameters["name"] == "status":
                        value = broker.status()
                    else:
                        raise ValueError("unknown tool")
                    result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
                except Exception as error:
                    result = {"isError": True, "content": [{"type": "text", "text": type(error).__name__ + ": " + str(error)}]}
            else:
                raise ValueError("unsupported MCP method")
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32603, "message": str(error)}}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
