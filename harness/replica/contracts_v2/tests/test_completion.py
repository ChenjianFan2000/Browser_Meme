import subprocess
import time
import uuid

import pytest

from harness.replica import transport
from harness.replica.contracts_v1 import runner as stable
from harness.replica.contracts_v2.runner import completion_deadline


def test_completion_cannot_extend_total_wall():
    assert completion_deadline(10, 20, 45, now=25) == 30


@pytest.mark.parametrize("duration,grace,expected", [(0.2, 2, 0), (4, 0.05, 143)])
def test_delayed_exit_and_bounded_termination_clean(tmp_path, duration, grace, expected):
    guard = transport._module("process_guard", runtime_source=stable.RUNTIME)
    receipt = tmp_path / "cleanup.json"
    ready = tmp_path / "child-ready"
    nonce = uuid.uuid4().hex
    child = subprocess.Popen([transport.PYTHON, str(stable.RUNTIME / "process_guard.py"), "--receipt", str(receipt), "--nonce", nonce,
                              "--", transport.PYTHON, "-c", "from pathlib import Path; import time; Path(" + repr(str(ready)) + ").write_text('ready'); time.sleep(" + str(duration) + ")"], start_new_session=True)
    # Allow the established supervisor to install handlers before exercising its
    # actual cleanup path. This is a process control, not a browser execution.
    admission_deadline = time.monotonic() + 3
    while not ready.exists() and time.monotonic() < admission_deadline:
        time.sleep(.01)
    assert ready.exists()
    started = time.monotonic()
    deadline = completion_deadline(started, 3, grace)
    while child.poll() is None and time.monotonic() < deadline:
        time.sleep(.01)
    stable.shared._terminate(child)
    assert child.returncode == 0 if expected == 0 else child.returncode != 0
    assert guard.receipt_valid(receipt, nonce=nonce, supervisor_pid=child.pid)
    assert time.monotonic() - started < 3
