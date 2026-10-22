"""Case-level dispatch across independent, admitted website workers."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
import json
from pathlib import Path
import queue
import random
import subprocess
import sys
import threading
import time

from .management import ROOT
from .records import sha256, write_new_json, freeze_manifest
from .report_v002 import checked_manifest, read, schedule_runs
from .run_batch import verify_frozen_learning
from .run_expanded_case_v001 import verify_registration
from .run_learning import EXPERIMENT


def available_memory_bytes():
    class Status(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended", ctypes.c_ulonglong)]
    status = Status()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("cannot measure host available memory")
    return status.avail_phys


def pending_cases(schedule, *, experiment=EXPERIMENT):
    runs = []
    preserved = []
    for worker, condition in schedule_runs(schedule):
        run_id = condition.lower() + "-seed-" + str(worker["seed"])
        order = list(range(1, 31))
        random.Random(worker["seed"]).shuffle(order)
        rows = []
        for index in order:
            directory = experiment / "evaluations" / run_id / f"case-{index:02d}"
            manifest = directory / "case-manifest.json"
            if manifest.exists():
                _, digest = checked_manifest(directory, "case-manifest.json", {"case-summary.json", "registration.json"})
                summary, registration = read(directory / "case-summary.json"), read(directory / "registration.json")
                if (summary.get("learning_run") != run_id or summary.get("case_index") != index
                        or summary.get("condition") != condition or summary.get("safe_to_reset") is not True
                        or registration.get("learning_run") != run_id or registration.get("index") != index
                        or registration.get("condition") != condition or registration.get("case_id") != summary.get("case_id")):
                    raise ValueError("completed case identity or reset safety is not confirmed")
                preserved.append({"run_id": run_id, "case_index": index, "case_manifest_sha256": digest})
            elif directory.exists():
                raise ValueError("partial case or administrative reservation must be explicitly resolved: " + str(directory))
            else:
                rows.append({"run_id": run_id, "condition": condition, "seed": worker["seed"], "case_index": index})
        runs.append(rows)
    # Each run retains its seeded relative dispatch order; six runs are interleaved.
    pending = [rows[index] for index in range(max(map(len, runs), default=0)) for rows in runs if index < len(rows)]
    if len(pending) + len(preserved) != 180:
        raise ValueError("registered denominator changed")
    return pending, preserved


def provider_failure(directory, summary):
    if summary.get("model_cli_exit_code") == 0:
        return None
    events = directory / "private/solar/events.jsonl"
    if not events.exists():
        return "model_cli_failed_without_event_archive"
    for line in events.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        nested = row.get("error")
        message = (str(row.get("message", "")) + " " +
                   str(nested.get("message", "") if isinstance(nested, dict) else nested or "")).lower()
        if row.get("type") in {"error", "turn.failed"} and any(part in message for part in (
                "workspace routing", "rate limit", "rate_limit", "unauthorized", "authentication",
                "connection", "reconnecting", "429", "401", "at capacity", "service unavailable")):
            return "model_provider_connection_or_availability_failure"
    if summary.get("model_cli_timeout") is True:
        return None
    return "model_cli_failure_before_ui" if not summary.get("ui_actions") else None


class MemoryGate:
    """Shared, bounded-cost host and WSL memory observations; failures stop dispatch."""
    def __init__(self, log):
        self.lock = threading.Lock()
        self.sampled = 0.0
        self.ready = False
        self.log = log

    def available(self):
        with self.lock:
            if time.monotonic() - self.sampled < 10:
                return self.ready
            windows = available_memory_bytes()
            code = "from pathlib import Path; print(next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))"
            result = subprocess.run(["wsl", "-d", "BrowserMeme-Ubuntu", "--", "python3", "-c", code],
                                    capture_output=True, text=True, timeout=20, creationflags=0x08000000)
            if result.returncode:
                raise RuntimeError("WSL available-memory measurement failed")
            wsl = int(result.stdout.strip())
            self.ready = windows >= 4 * 1024 ** 3 and wsl >= 2 * 1024 ** 3
            self.sampled = time.monotonic()
            self.log({"event": "memory_admission", "windows_available_bytes": windows,
                      "wsl_available_bytes": wsl, "new_dispatch_allowed": self.ready})
            return self.ready


class DispatchQueue:
    def __init__(self, cases):
        self.queue = queue.Queue()
        for case in cases:
            self.queue.put(case)
        self.lock = threading.Lock()
        self.stopped = threading.Event()

    def take(self):
        with self.lock:
            if self.stopped.is_set():
                return None
            try:
                return self.queue.get_nowait()
            except queue.Empty:
                return None

    def stop(self):
        with self.lock:
            self.stopped.set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expansion-registration", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--max-workers", type=int, default=12)
    args = parser.parse_args()
    registration_path = Path(args.expansion_registration).resolve(strict=True)
    registration = verify_registration(registration_path)
    workers = registration["workers"]
    if not 1 <= args.max_workers <= registration["max_active_workers"] or args.max_workers > len(workers):
        raise ValueError("worker count is outside admission")
    if (len({row["id"] for row in workers}) != len(workers)
            or len({str(Path(row["runtime"]).resolve()).lower() for row in workers}) != len(workers)
            or len({row["frontend_port"] for row in workers}) != len(workers)):
        raise ValueError("worker identities, runtimes or ports alias")
    schedule_path = EXPERIMENT / "FORMAL_SCHEDULE.json"
    if sha256(schedule_path) != registration["formal_schedule_sha256"]:
        raise ValueError("formal schedule differs from expansion parent")
    schedule = read(schedule_path)
    for worker, condition in schedule_runs(schedule):
        verify_frozen_learning(worker, condition)
    cases, preserved = pending_cases(schedule)
    batch = EXPERIMENT / "batches" / args.batch_id
    batch.mkdir(parents=True, exist_ok=False)
    (batch / "claims").mkdir()
    (batch / "logs").mkdir()
    write_new_json(batch / "dispatch-plan.json", {
        "created_ns": time.time_ns(), "expansion_registration_sha256": sha256(registration_path),
        "actual_max_workers": args.max_workers, "pending": cases, "preserved": preserved,
        "available_memory_admission_bytes": 4 * 1024 ** 3,
        "wsl_available_memory_admission_bytes": 2 * 1024 ** 3, "case_denominator": 180})
    dispatch = DispatchQueue(cases)
    journal_lock = threading.Lock()
    outcomes = []

    def log(event):
        value = {"time_ns": time.time_ns(), **event}
        with journal_lock:
            with (batch / "dispatch-events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(value, ensure_ascii=False) + "\n")
            print(json.dumps(value), flush=True)

    memory = MemoryGate(log)

    def worker_loop(worker):
        results = []
        while not dispatch.stopped.is_set():
            while not memory.available():
                if (batch / "STOP_DISPATCH").exists():
                    dispatch.stop()
                if dispatch.stopped.wait(2):
                    return results
            if (batch / "STOP_DISPATCH").exists():
                dispatch.stop()
            case = dispatch.take()
            if case is None:
                return results
            label = case["run_id"] + f"-case-{case['case_index']:02d}"
            claim = {**case, "worker": worker["id"], "runtime": worker["runtime"],
                     "frontend_port": worker["frontend_port"], "claimed_ns": time.time_ns(),
                     "expansion_registration_sha256": sha256(registration_path)}
            write_new_json(batch / "claims" / (label + ".json"), claim)
            command = [sys.executable, "-m", "harness.phase2.run_expanded_case_v001",
                       "--expansion-registration", str(registration_path), "--worker", worker["id"],
                       "--learning-run", case["run_id"], "--case-index", str(case["case_index"])]
            log({"event": "dispatch", **claim})
            with (batch / "logs" / (label + ".stdout.jsonl")).open("xb") as stdout, (batch / "logs" / (label + ".stderr.txt")).open("xb") as stderr:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr, creationflags=0x08000000)
                log({"event": "case_process_started", "label": label, "worker": worker["id"], "pid": child.pid})
                code = child.wait()
            directory = EXPERIMENT / "evaluations" / case["run_id"] / f"case-{case['case_index']:02d}"
            result = {**case, "worker": worker["id"], "exit_code": code, "case_archived": (directory / "case-manifest.json").is_file()}
            if code or not result["case_archived"]:
                result["dispatch_stopping_reason"] = "case_management_failure_requires_explicit_recovery"
                dispatch.stop()
            else:
                summary = read(directory / "case-summary.json")
                if summary.get("safe_to_reset") is not True:
                    result["dispatch_stopping_reason"] = "reset_safety_not_confirmed"
                    dispatch.stop()
                else:
                    failure = provider_failure(directory, summary)
                    if failure:
                        result["dispatch_stopping_reason"] = failure
                        dispatch.stop()
            results.append(result)
            log({"event": "case_process_finished", **result})
        return results

    started_ns = time.time_ns()
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = {pool.submit(worker_loop, worker): worker["id"] for worker in workers[:args.max_workers]}
        for future in as_completed(futures):
            try:
                outcomes.extend(future.result())
            except Exception as error:
                dispatch.stop()
                outcomes.append({"worker": futures[future], "error": type(error).__name__ + ": " + str(error)})
    summary = {"started_ns": started_ns, "finished_ns": time.time_ns(), "batch_id": args.batch_id,
               "expansion_registration_sha256": sha256(registration_path), "outcomes": outcomes,
               "unclaimed": list(dispatch.queue.queue), "dispatch_stopped": dispatch.stopped.is_set(),
               "original_case_results_rewritten": False}
    write_new_json(batch / "batch-summary.json", summary)
    freeze_manifest(batch, [path.relative_to(batch).as_posix() for path in batch.rglob("*") if path.is_file()], batch / "batch-manifest.json")
    print(json.dumps({"batch_id": args.batch_id, "attempts": len(outcomes), "unclaimed": dispatch.queue.qsize(), "stopped": dispatch.stopped.is_set()}), flush=True)
    if dispatch.stopped.is_set():
        raise SystemExit(2)


if __name__ == "__main__":
    main()
