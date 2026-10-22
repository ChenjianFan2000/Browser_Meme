"""Trusted Linux launcher for one independent exact-Solar experimental session."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from process_guard import receipt_valid
from permissions import CODEX, overrides, toml_inline


def launch(plan):
    private = Path(plan["private"])
    private.mkdir(parents=True, exist_ok=True)
    home = Path(plan["codex_home"])
    if {item.name for item in home.iterdir()} != {"auth.json"}:
        raise ValueError("new learner home must contain only the authentication file")
    config = plan["broker_config"]
    args = [CODEX, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
            "--strict-config", "--skip-git-repo-check", "-m", "gpt-6.1-sol",
            "-C", plan["workspace"], "--json", "-o", str(private / "last-message.txt")]
    args += overrides(extra_paths={path: "read" for path in plan.get("readonly_paths", [])})
    args += ["-c", "model_reasoning_effort=" + toml_inline(plan.get("reasoning_effort", "high"))]
    if config:
        broker_file = plan.get("broker_file", "browser_broker.py")
        approval_tools = {"execute_script": {"approval_mode": "approve"},
                          "status": {"approval_mode": "approve"}}
        if broker_file == "evaluation_broker.py":
            approval_tools["declare_task_prediction"] = {"approval_mode": "approve"}
            if plan["condition"] == "A":
                approval_tools["model_predict"] = {"approval_mode": "approve"}
        args += ["-c", "mcp_servers.phase2=" + toml_inline({
            "command": "/usr/bin/python3",
            "args": [str(Path(plan["runtime"]) / broker_file), "--config", config],
            "enabled": True, "startup_timeout_sec": 20, "tool_timeout_sec": 330,
            "tools": approval_tools,
        })]
    args += ["-"]
    env = {"PATH": "/usr/bin:/bin", "HOME": "/home/research", "CODEX_HOME": plan["codex_home"],
           "LANG": "C.UTF-8", "NO_PROXY": "", "no_proxy": ""}
    prompt = Path(plan["prompt_path"]).read_bytes()
    cleanup_nonce = uuid.uuid4().hex
    cleanup_receipt = private / ("cleanup-" + cleanup_nonce + ".json")
    started = time.monotonic()
    with (private / "events.jsonl").open("xb") as out, (private / "stderr.txt").open("xb") as err:
        child = subprocess.Popen([sys.executable, str(Path(plan["runtime"]) / "process_guard.py"),
                                  "--receipt", str(cleanup_receipt), "--nonce", cleanup_nonce, "--", *args], stdin=subprocess.PIPE, stdout=out, stderr=err,
                                 env=env, start_new_session=True)
        child.stdin.write(prompt)
        child.stdin.close()
        timeout = False
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
    for line in (private / "events.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
            if "usage" in event:
                usage.append(event["usage"])
        except ValueError:
            pass
    tree_clean = receipt_valid(cleanup_receipt, nonce=cleanup_nonce, supervisor_pid=child.pid)
    result = {"process_tree_clean": tree_clean, "cleanup_receipt": cleanup_receipt.name,
              "cleanup_nonce": cleanup_nonce, "supervisor_pid": child.pid, "model": "gpt-6.1-sol", "fresh_context": True, "exit_code": code,
              "timeout": timeout, "elapsed_seconds": time.monotonic() - started,
              "usage_events": usage, "model_calls": None, "cost": None,
              "launch_channel": "standalone_codex_cli_child", "command": args}
    with (private / "launch-result.json").open("x") as out:
        json.dump(result, out, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "command"}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    launch(json.loads(Path(args.plan).read_text(encoding="utf-8")))
