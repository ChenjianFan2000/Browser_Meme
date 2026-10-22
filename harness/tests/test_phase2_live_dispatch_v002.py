from contextlib import nullcontext
import pytest
from harness.phase2 import run_parallel_v002 as dispatch


def test_all_registered_frontends_and_backends_are_checked():
    seen = []
    def connect(address, *, timeout):
        seen.append((address, timeout))
        return nullcontext()
    workers = [{"id": "a", "frontend_port": 13042, "backend_port": 13138},
               {"id": "b", "frontend_port": 14042, "backend_port": 14138}]
    assert len(dispatch.check_services(workers, connect=connect)) == 4
    assert [value[0][1] for value in seen] == [13042, 13138, 14042, 14138]


def test_dead_backend_stops_before_queue_claim(monkeypatch):
    def connect(address, *, timeout):
        if address[1] == 13138:
            raise ConnectionRefusedError("synthetic stopped backend")
        return nullcontext()
    workers = [{"id": "a", "frontend_port": 13042, "backend_port": 13138}]
    real_check = dispatch.check_services
    monkeypatch.setattr(dispatch, "check_services", lambda rows: real_check(rows, connect=connect))
    monkeypatch.setattr(dispatch.previous.MemoryGate, "available", lambda self: True)
    queue = dispatch.previous.DispatchQueue([1, 2])
    gate = dispatch.memory_gate_type(workers)(lambda event: None)
    with pytest.raises(RuntimeError, match="before case claim"):
        if gate.available():
            queue.take()
    assert queue.queue.qsize() == 2


def test_memory_shortage_does_not_launch_connection_probes(monkeypatch):
    monkeypatch.setattr(dispatch.previous.MemoryGate, "available", lambda self: False)
    monkeypatch.setattr(dispatch, "check_services", lambda workers: pytest.fail("no readiness until memory admission"))
    gate = dispatch.memory_gate_type([])(lambda event: None)
    assert gate.available() is False
