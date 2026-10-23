"""Bound arbitrary independent callbacks using the existing subreaper cleanup."""
from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
from pathlib import Path
import signal
import time
import uuid


def _supervise(adapter, connection, receipt, nonce, expected_parent, guard):
    os.setsid()
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0 or libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "oracle supervisor prctl failed")
    if os.getppid() != expected_parent:
        stopped = True
    worker = None
    try:
        if not stopped:
            worker = os.fork()
            if worker == 0:
                for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                    signal.signal(sig, signal.SIG_DFL)
                try:
                    while True:
                        method, args = connection.recv()
                        if method == "@close":
                            break
                        try:
                            connection.send({"ok": True, "value": getattr(adapter, method)(*args)})
                        except Exception as error:
                            connection.send({"ok": False, "error": type(error).__name__ + ": " + str(error)})
                except (EOFError, BrokenPipeError):
                    pass
                finally:
                    connection.close()
                    os._exit(0)
            connection.close()
            while not stopped:
                ended, _ = os.waitpid(worker, os.WNOHANG)
                if ended:
                    break
                time.sleep(.02)
    finally:
        guard.terminate_owned(timeout=10)
        with Path(receipt).open("x") as stream:
            json.dump({"status": "cleaned", "owned_processes_remaining": 0,
                       "supervisor_pid": os.getpid(), "nonce": nonce,
                       "cleaned_at_ns": time.time_ns()}, stream)
            stream.flush()
            os.fsync(stream.fileno())


class BoundedOracle:
    """Adapter state persists in one child; callbacks cannot outlive a timeout cleanup."""
    def __init__(self, adapter, *, deadline, call_seconds, receipt, guard):
        self.deadline, self.call_seconds = deadline, call_seconds
        self.receipt, self.nonce, self.guard = Path(receipt), uuid.uuid4().hex, guard
        parent, child = multiprocessing.get_context("fork").Pipe()
        self.connection = parent
        self.process = multiprocessing.get_context("fork").Process(
            target=_supervise, args=(adapter, child, str(receipt), self.nonce, os.getpid(), guard))
        self.process.start()
        child.close()
        self.closed = False
        self.clean = False

    def call(self, method, *args):
        if self.closed:
            raise TimeoutError("oracle worker is closed")
        remaining = min(self.call_seconds, self.deadline - time.monotonic())
        if remaining <= 0:
            self.close(force=True)
            raise TimeoutError("run deadline exhausted before oracle call")
        try:
            self.connection.send((method, args))
            if not self.connection.poll(remaining):
                self.close(force=True)
                raise TimeoutError("independent oracle " + method + " exceeded bounded call deadline")
            result = self.connection.recv()
        except TimeoutError:
            raise
        except (EOFError, BrokenPipeError, OSError) as error:
            self.close(force=True)
            raise RuntimeError("independent oracle process unavailable") from error
        if not result["ok"]:
            raise RuntimeError(result["error"])
        return result["value"]

    def describe(self):
        return self.call("describe")

    def prepare(self, *args):
        return self.call("prepare", *args)

    def capture(self, *args):
        return self.call("capture", *args)

    def assess(self, *args):
        return self.call("assess", *args)

    def close(self, *, force=False):
        if self.closed:
            return self.clean
        self.closed = True
        if self.process.is_alive():
            if force:
                self.process.terminate()
            else:
                try:
                    self.connection.send(("@close", ()))
                except (EOFError, BrokenPipeError, OSError):
                    pass
            self.process.join(timeout=12)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=2)
        self.connection.close()
        self.clean = self.guard.receipt_valid(self.receipt, nonce=self.nonce, supervisor_pid=self.process.pid)
        return self.clean
