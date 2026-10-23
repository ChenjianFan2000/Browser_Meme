"""Owned-process watchdog with separate liveness and evidence-progress signals."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

try:
    from .runtime.process_guard import receipt_valid, snapshot
except ImportError:
    from runtime.process_guard import receipt_valid, snapshot


def resources(path):
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        if key == "MemAvailable":
            values["available_memory_bytes"] = int(value.strip().split()[0]) * 1024
    stat = os.statvfs(path)
    values["available_disk_bytes"] = stat.f_bavail * stat.f_frsize
    return values


def process_sample(pid):
    try:
        info = {}
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in {"State", "VmRSS", "Threads"}:
                info[key] = value.strip()
        return {"pid": pid, "alive": True, **info}
    except FileNotFoundError:
        return {"pid": pid, "alive": False}


def progress_sample(paths):
    result = []
    for name in paths:
        path = Path(name)
        if path.exists():
            st = path.stat()
            result.append((str(path), st.st_size, st.st_mtime_ns))
    return result


def terminate_group(child):
    if child.poll() is not None:
        return
    os.killpg(child.pid, signal.SIGTERM)
    try:
        # process_guard reserves 15 seconds to kill/reap its owned tree before
        # writing the receipt; let that bounded cleanup finish before escalation.
        child.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=10)


def supervise(command, out, *, timeout=1800, idle_timeout=180,
              progress_paths=(), min_memory_bytes=1024**3, min_disk_bytes=512*1024**2,
              interval=5, startup_timeout=10):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    start = last_progress = time.monotonic()
    previous = None
    reason = None
    startup_complete = False
    nonce = uuid.uuid4().hex
    receipt = out / "cleanup.json"
    guarded_command = [sys.executable, str(Path(__file__).parent / "runtime/process_guard.py"),
                       "--receipt", str(receipt), "--nonce", nonce, "--", *command]
    with (out / "stdout.log").open("xb") as stdout, (out / "stderr.log").open("xb") as stderr:
        # The subreaper owns detached/orphaned descendants even after the
        # command's leader exits. Killing only its initial process group cannot
        # provide that guarantee.
        child = subprocess.Popen(guarded_command, stdout=stdout, stderr=stderr, start_new_session=True)
        with (out / "heartbeat.jsonl").open("x") as events:
            try:
                while True:
                    now = time.monotonic()
                    # Guard setup installs subreaper/signal handling before it
                    # forks the command. Do not consume the command's idle
                    # allowance while that separate bounded startup is pending.
                    if not startup_complete:
                        startup_complete = any(row[0] == child.pid for row in snapshot().values())
                        last_progress = now
                    # Logs show activity, not evidence progress. Only explicitly
                    # registered evidence paths may reset the idle deadline.
                    signal_state = progress_sample(progress_paths)
                    if signal_state != previous:
                        previous, last_progress = signal_state, now
                    sample = {"time_ns": time.time_ns(), "elapsed_seconds": now-start,
                              "idle_seconds": now-last_progress, "process": process_sample(child.pid),
                              "supervisor_startup_complete": startup_complete,
                              "resources": resources(out), "progress_signals": signal_state,
                              "log_activity": progress_sample([out / "stdout.log", out / "stderr.log"])}
                    events.write(json.dumps(sample) + "\n")
                    events.flush()
                    temp = out / "status.next.json"
                    temp.write_text(json.dumps(sample, indent=2))
                    temp.replace(out / "status.json")
                    if child.poll() is not None:
                        reason = "completed" if child.returncode == 0 else "process_failure"
                        break
                    if (out / "STOP").exists():
                        reason = "coordinator_stop"
                    elif now-start >= timeout:
                        reason = "wall_time_exhausted"
                    elif not startup_complete and now-start >= startup_timeout:
                        reason = "supervisor_startup_timeout"
                    elif startup_complete and now-last_progress >= idle_timeout:
                        reason = "no_evidence_progress"
                    elif sample["resources"]["available_memory_bytes"] < min_memory_bytes:
                        reason = "memory_guard"
                    elif sample["resources"]["available_disk_bytes"] < min_disk_bytes:
                        reason = "disk_guard"
                    if reason:
                        terminate_group(child)
                        break
                    time.sleep(interval)
            finally:
                terminate_group(child)
    tree_clean = receipt_valid(receipt, nonce=nonce, supervisor_pid=child.pid)
    if not tree_clean:
        reason = "process_tree_cleanup_unconfirmed"
    result = {"reason": reason, "exit_code": child.returncode,
              "elapsed_seconds": time.monotonic()-start, "pid": child.pid,
              "command": command, "automatic_retry": False,
              "process_tree_clean": tree_clean, "cleanup_receipt": str(receipt),
              "supervision_policy": {"wall_seconds": timeout, "idle_seconds": idle_timeout,
                  "startup_seconds": startup_timeout, "sample_interval_seconds": interval,
                  "min_memory_bytes": min_memory_bytes, "min_disk_bytes": min_disk_bytes},
              "meaning": "runtime supervision; successful process exit is not experiment success"}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--idle-timeout", type=float, default=180)
    parser.add_argument("--startup-timeout", type=float, default=10)
    parser.add_argument("--progress", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command required")
    result = supervise(command, args.out, timeout=args.timeout,
                       idle_timeout=args.idle_timeout, startup_timeout=args.startup_timeout,
                       progress_paths=args.progress)
    print(json.dumps(result))
    return 0 if result["reason"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
