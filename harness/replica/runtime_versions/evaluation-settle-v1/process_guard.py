"""Linux trusted subprocess supervisor; never mounted in learner namespaces."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def snapshot():
    rows = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / 'stat').read_text(encoding='utf-8')
            fields = raw[raw.rfind(')') + 2:].split()
            rows[int(entry.name)] = (int(fields[1]), fields[19], fields[0])
        except (OSError, ValueError):
            pass
    return rows


def terminate_owned(timeout=15):
    deadline = time.monotonic() + timeout
    while True:
        rows = snapshot()
        owned = {os.getpid()}
        while True:
            expanded = owned | {pid for pid, row in rows.items() if row[0] in owned}
            if expanded == owned:
                break
            owned = expanded
        owned.discard(os.getpid())
        for pid in owned:
            # Match kernel starttime again immediately before signaling.
            current = snapshot().get(pid)
            if current and current[1] == rows[pid][1]:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        while True:
            try:
                if os.waitpid(-1, os.WNOHANG)[0] == 0:
                    break
            except ChildProcessError:
                return
        if time.monotonic() >= deadline:
            raise RuntimeError('owned_process_tree_unsettled')
        time.sleep(.02)


def receipt_valid(path, *, nonce, supervisor_pid):
    try:
        path = Path(path)
        if path.is_symlink() or not nonce or not isinstance(supervisor_pid, int):
            return False
        value = json.loads(path.read_text(encoding="utf-8"))
        return (value.get("status") == "cleaned" and value.get("owned_processes_remaining") == 0
                and value.get("nonce") == nonce and value.get("supervisor_pid") == supervisor_pid)
    except (OSError, ValueError, TypeError):
        return False


def main():
    command = sys.argv[1:]
    receipt = None
    nonce = None
    if command[:1] == ["--receipt"]:
        if len(command) < 6 or command[2] != "--nonce" or command[4] != "--":
            raise ValueError("expected --receipt PATH --nonce NONCE -- COMMAND")
        receipt, nonce = Path(command[1]), command[3]
        command = command[5:]
        if not nonce or receipt.exists():
            raise ValueError("cleanup receipt must be new")
    parent = os.getppid()
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0 or libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'prctl supervisor setup failed')
    if os.getppid() != parent:
        stopped = True
    child = None
    try:
        if not stopped:
            child = subprocess.Popen(command)
        while child is not None and child.poll() is None and not stopped:
            time.sleep(.02)
        code = child.returncode if child is not None and child.returncode is not None else 143
    finally:
        terminate_owned()
    if receipt is not None:
        with receipt.open("x", encoding="utf-8") as out:
            json.dump({"status": "cleaned", "owned_processes_remaining": 0,
                       "supervisor_pid": os.getpid(), "nonce": nonce,
                       "child_exit_code": code, "cleaned_at_ns": time.time_ns()}, out)
            out.flush()
            os.fsync(out.fileno())
    raise SystemExit(code)


if __name__ == '__main__':
    main()
