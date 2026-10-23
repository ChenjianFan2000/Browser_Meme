"""Real bounded callback subprocesses; no browser or website process is started."""
import json
import os
from pathlib import Path
import time

import pytest

from harness.replica import transport
from harness.replica.contracts_v1 import runner
from harness.replica.contracts_v1.oracle_process import BoundedOracle


class StatefulOracle:
    def __init__(self):
        self.count = 0

    def describe(self):
        return {"independent": True, "callback_pid": os.getpid()}

    def prepare(self, *args):
        self.count += 1
        return {"count": self.count, "callback_pid": os.getpid()}

    def capture(self, *args):
        self.count += 1
        return {"count": self.count, "callback_pid": os.getpid()}

    def assess(self, *args):
        self.count += 1
        return {"count": self.count, "callback_pid": os.getpid()}


class SleepingOracle(StatefulOracle):
    def prepare(self, *args):
        time.sleep(2)
        return {"count": "must not return"}


def guard_module():
    return transport._module("process_guard", runtime_source=runner.RUNTIME)


def assert_clean(proxy, callback_pid=None):
    assert proxy.close() is True
    assert proxy.closed and proxy.clean
    assert proxy.process.is_alive() is False
    receipt = json.loads(proxy.receipt.read_text())
    assert receipt["status"] == "cleaned"
    assert receipt["owned_processes_remaining"] == 0
    assert proxy.guard.receipt_valid(proxy.receipt, nonce=proxy.nonce, supervisor_pid=proxy.process.pid)
    if callback_pid is not None:
        assert not Path("/proc", str(callback_pid)).exists()


def test_bounded_oracle_preserves_state_across_callbacks_and_cleans_process(tmp_path):
    adapter = StatefulOracle()
    proxy = BoundedOracle(adapter, deadline=time.monotonic() + 3, call_seconds=.5,
                          receipt=tmp_path / "cleanup.json", guard=guard_module())
    try:
        description = proxy.describe()
        callback_pid = description["callback_pid"]
        assert callback_pid not in {os.getpid(), proxy.process.pid}
        assert proxy.prepare("source", "fixture")["count"] == 1
        assert proxy.capture("source", "fixture", {})["count"] == 2
        result = proxy.assess("fixture", {}, {}, {}, {})
        assert result == {"count": 3, "callback_pid": callback_pid}
        assert adapter.count == 0
    finally:
        assert_clean(proxy, locals().get("callback_pid"))


def test_callback_timeout_under_half_second_kills_actual_callback_process(tmp_path):
    proxy = BoundedOracle(SleepingOracle(), deadline=time.monotonic() + 3, call_seconds=.05,
                          receipt=tmp_path / "cleanup.json", guard=guard_module())
    callback_pid = None
    try:
        callback_pid = proxy.describe()["callback_pid"]
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="exceeded bounded call deadline"):
            proxy.prepare("source", "fixture")
        assert time.monotonic() - started < .5
        assert proxy.closed and proxy.clean
    finally:
        assert_clean(proxy, callback_pid)


def test_run_wall_budget_bounds_prepare_before_any_browser_launch(tmp_path, monkeypatch):
    reached = []

    def preparation_only(*args, oracle, started, **kwargs):
        reached.append("prepare")
        oracle.prepare("source", "fixture")
        reached.append("browser-launch-would-follow")
        raise AssertionError("sleeping prepare must exceed wall budget")

    monkeypatch.setattr(runner, "_run_source", preparation_only)
    started = time.monotonic()
    result = runner.run_source({}, "unused.py", tmp_path / "run", "unused.json", oracle=SleepingOracle(),
                               policy={"wall_seconds": .05, "oracle_call_seconds": 1})
    assert time.monotonic() - started < .5
    assert reached == ["prepare"]
    assert result["primary_pass"] is False
    assert result["checked_actions"] == 0
    assert result["reason"] == "controller_preflight_error"
    assert "TimeoutError" in result["first_failure"]["error"]
    assert result["oracle_process_tree_clean"] is True
    receipt = json.loads((tmp_path / "run/oracle-cleanup.json").read_text())
    assert receipt["status"] == "cleaned" and receipt["owned_processes_remaining"] == 0


def test_elapsed_preparation_budget_prevents_dispatching_next_callback(tmp_path):
    proxy = BoundedOracle(StatefulOracle(), deadline=time.monotonic() + .05, call_seconds=1,
                          receipt=tmp_path / "cleanup.json", guard=guard_module())
    try:
        callback_pid = proxy.describe()["callback_pid"]
        time.sleep(.06)
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="run deadline exhausted before oracle call"):
            proxy.prepare("source", "fixture")
        assert time.monotonic() - started < .5
    finally:
        assert_clean(proxy, locals().get("callback_pid"))
