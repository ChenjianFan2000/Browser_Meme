"""Add live service checks before claiming a new case; reuse the frozen queue."""
from __future__ import annotations

import argparse
from pathlib import Path
import socket
import threading

from . import run_parallel_v001 as previous
from .records import sha256
from .run_expanded_case_v001 import verify_registration


def check_services(workers, connect=socket.create_connection):
    observations = []
    for worker in workers:
        for role in ("frontend", "backend"):
            port = worker[role + "_port"]
            try:
                with connect(("127.0.0.1", port), timeout=2):
                    pass
            except OSError as error:
                raise RuntimeError(f"worker {worker['id']} {role} no longer accepts connections; stop before case claim") from error
            observations.append({"worker": worker["id"], "role": role, "port": port})
    return observations


def memory_gate_type(workers):
    original = previous.MemoryGate

    class LiveServiceMemoryGate(original):
        def __init__(self, log):
            super().__init__(log)
            self.service_lock = threading.Lock()
            self.service_checks = 0

        def available(self):
            ready = super().available()
            if ready:
                with self.service_lock:
                    observations = check_services(workers)
                    self.service_checks += 1
                    self.log({"event": "live_services_before_case_claim", "check_number": self.service_checks,
                              "connections": observations, "qualification": "TCP liveness only; deployment and UI admission remain independently required"})
            return ready
    return LiveServiceMemoryGate


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--expansion-registration", required=True)
    args, _ = parser.parse_known_args()
    registration = verify_registration(args.expansion_registration)
    relative = Path(__file__).resolve().relative_to(previous.ROOT.resolve()).as_posix()
    expected = {item["path"]: item["sha256"] for item in registration["management_inputs"]}
    if registration.get("dispatcher_entry") != relative or expected.get(relative) != sha256(Path(__file__)):
        raise ValueError("actual v002 dispatcher must be explicitly registered and hash-bound")
    workers = registration["workers"]
    ports = [worker[role + "_port"] for worker in workers for role in ("frontend", "backend")]
    if len(ports) != len(set(ports)):
        raise ValueError("registered frontend/backend ports alias")
    previous.MemoryGate = memory_gate_type(workers)
    previous.main()


if __name__ == "__main__":
    main()
