"""Site-independent, fail-closed live review gates for protocol 3."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import uuid

from .artifacts import digest
from .contract import require


class GateStopped(RuntimeError):
    pass


def validate_supervision(plan):
    if plan["schema_version"] == 2:
        require(not plan.get("supervision"), "protocol 2 cannot declare supervision")
        require(all(not c.get("checkpoints") for c in plan["cases"]), "checkpoints require protocol 3")
        return
    config = plan.get("supervision", {})
    for key, maximum in (("case_seconds", 900), ("review_timeout_seconds", 240),
                         ("max_reviews_per_case", 3)):
        require(type(config.get(key)) is int and 0 < config[key] <= maximum, f"invalid supervision {key}")
    require(config.get("on_step_failure") == "diagnose_and_stop", "failure policy must stop")
    for case in plan["cases"]:
        gates = case.get("checkpoints", [])
        require(gates and len(gates) < config["max_reviews_per_case"],
                "reserve one review for failure diagnosis")
        require(len({g["id"] for g in gates}) == len(gates), "duplicate checkpoint id")
        order = {step["id"]: i for i, step in enumerate(case["steps"])}
        for gate in gates:
            require(re.fullmatch(r"[A-Za-z0-9_-]+", gate["id"]), "unsafe checkpoint id")
            require(gate.get("before_step") in order and gate.get("reason"), "invalid checkpoint")
            required = gate.get("required_readouts", [])
            require(isinstance(required, list) and all(isinstance(key, str) for key in required)
                    and set(required) <= set(plan.get("readouts", {})), "unknown required gate readout")
        positions = [order[g["before_step"]] for g in gates]
        require(positions == sorted(set(positions)), "checkpoint order must be unique and increasing")


def evaluate_gate(value):
    if not isinstance(value, dict):
        return False
    checks = value.get("checks")
    return (
        value.get("decision") == "continue"
        and isinstance(checks, list) and bool(checks)
        and len({c.get("id") for c in checks if isinstance(c, dict)}) == len(checks)
        and all(isinstance(c, dict) and isinstance(c.get("id"), str)
                and bool(c["id"]) and c.get("passed") is True for c in checks)
    )


def state_fingerprint(observation):
    # Exclude growing network logs, timing and full rendered DOM from comparison.
    # Real UI fields and independent persisted state must be unchanged.
    ui = observation.get("ui", {})
    state = {
        "ui": {key: ui.get(key) for key in ("url", "text", "fields")},
        "backend": observation.get("backend"),
        "independent_ui": observation.get("independent_ui"),
        "observation_errors": observation.get("observation_errors"),
    }
    return hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_decision(value, request, request_hash, folder, evidence_hashes, failure=False):
    require(isinstance(value, dict), "review decision must be an object")
    require(value.get("request_id") == request["request_id"], "stale review request id")
    require(value.get("request_sha256") == request_hash, "review request hash mismatch")
    require(value.get("reviewer") == "gpt-6.1-sol", "incorrect review model")
    require(value.get("decision") in ("continue", "stop"), "unsupported review decision")
    require(not failure or value["decision"] == "stop", "failure reviews cannot authorize continuation")
    require(value.get("classification") in (
        "planned_review", "locator", "timing", "implementation", "business_rule", "unconfirmed"
    ), "missing review classification")
    require(isinstance(value.get("reason"), str) and value["reason"].strip(), "missing review rationale")
    require(isinstance(value.get("evidence"), list) and value["evidence"], "review needs evidence")
    root = folder.resolve()
    for entry in value["evidence"]:
        require(isinstance(entry, str), "invalid review evidence")
        path = (folder / entry).resolve()
        require(path.is_relative_to(root) and path.is_file(), "review evidence escapes packet or is missing")
        require(entry == "request.json" or entry in evidence_hashes, "review must cite frozen public evidence")
    require(digest(folder / "request.json") == request_hash, "request changed during review")
    for name, expected in evidence_hashes.items():
        path = folder / name
        require(path.is_file() and digest(path) == expected, "public evidence changed during review")


class Supervisor:
    def __init__(self, monitor, writer):
        self.h = monitor
        self.write = writer
        self.config = monitor._plan["supervision"]
        self.gates = monitor._case_plan["checkpoints"]
        self.records = []
        self.grants = {}
        self.consumed = set()
        self.started = time.monotonic()
        self.diagnosed = False

    def _independent(self, checkpoint_id, current):
        ui = current.get("ui")
        gate = next((g for g in self.gates if g["id"] == checkpoint_id), {})
        missing = (
            not isinstance(ui, dict) or not isinstance(current.get("backend"), dict)
            or not isinstance(ui.get("url"), str) or not isinstance(ui.get("text"), str)
            or not isinstance(ui.get("fields"), dict)
        )
        if callable(getattr(self.h._adapter, "observe_ui", None)):
            missing = missing or not isinstance(current.get("independent_ui"), dict)
        if not missing:
            missing = any(key in ui.get("errors", {}) or ui["fields"].get(key) is None
                          for key in gate.get("required_readouts", []))
        if current.get("observation_errors") or missing:
            return {"decision": "unknown", "checks": [], "public_summary": "Incomplete observation."}
        try:
            value = self.h._adapter.checkpoint(
                copy.deepcopy(self.h.case), checkpoint_id, copy.deepcopy(self.h.initial),
                copy.deepcopy(current), copy.deepcopy(self.h.history)
            )
            if not isinstance(value, dict):
                raise ValueError("checkpoint evaluator returned a non-object")
            if not isinstance(value.get("public_summary", ""), str):
                raise ValueError("public summary must be a string")
            return value
        except Exception as exc:
            return {"decision": "unknown", "checks": [], "public_summary": "Independent evaluation failed.",
                    "private_error": str(exc)}

    def _public_verdict(self, value):
        # Never forward private check details or privileged observation fields.
        return {
            "decision": value.get("decision", "unknown"),
            "checks": [
                {"id": check.get("id") if isinstance(check.get("id"), str) else "invalid",
                 "passed": check.get("passed") if type(check.get("passed")) is bool else None}
                for check in value.get("checks", []) if isinstance(check, dict)
            ] if isinstance(value.get("checks"), list) else [],
            "public_summary": value.get("public_summary", ""),
        }

    def _review(self, checkpoint_id, trigger, pending_step, current, evaluation, error=None):
        if len(self.records) >= self.config["max_reviews_per_case"]:
            raise GateStopped("unconfirmed: live review budget exhausted")
        relative = Path("interventions") / f"{len(self.records) + 1:02d}-{checkpoint_id}"
        folder = self.h._out / relative
        folder.mkdir(parents=True, exist_ok=False)
        private_folder = self.h._out / "private-supervision" / folder.name
        private_folder.mkdir(parents=True, exist_ok=False)
        record = {"checkpoint_id": checkpoint_id, "trigger": trigger, "before_step": pending_step,
                  "directory": relative.as_posix(), "status": "preparing"}
        self.records.append(record)
        start = time.monotonic()
        try:
            self.write(private_folder / "evaluation.json", evaluation)
            self.h._capture((relative / "ui").as_posix())
            public_files = [folder / "ui.dom.json", folder / "ui.png"]
            notes = self.h._out / "notes"
            if notes.is_dir():
                (folder / "notes").mkdir()
                for source in sorted(notes.glob("*.json")):
                    destination = folder / "notes" / source.name
                    shutil.copyfile(source, destination)
                    public_files.append(destination)
            hashes = {path.relative_to(folder).as_posix(): digest(path) for path in public_files}
            request = {
                "request_id": uuid.uuid4().hex, "case": self.h.case,
                "checkpoint_id": checkpoint_id, "trigger": trigger, "before_step": pending_step,
                "reviewer": "gpt-6.1-sol", "ui": current.get("ui"),
                "independent": self._public_verdict(evaluation),
                "error": error, "public_evidence_sha256": hashes,
                "allowed_decisions": ["stop"] if trigger == "failure" else ["continue", "stop"],
                "timeout_seconds": self.config["review_timeout_seconds"],
                "privacy": "Review only this public packet; do not read private-supervision, backend snapshots or evaluator source.",
            }
            self.write(folder / "request.json", request)
            request_hash = digest(folder / "request.json")
            # Bind exactly the redacted serialized packet received by the reviewer.
            request = json.loads((folder / "request.json").read_text(encoding="utf-8"))
            record.update(status="waiting", request_id=request["request_id"], request_sha256=request_hash)
            self.h._recorder.emit("intervention_requested", **record)
            print(json.dumps({"intervention_requested": str(folder / "request.json"),
                              "request_sha256": request_hash}), flush=True)
            deadline = start + self.config["review_timeout_seconds"]
            decision_path = folder / "decision.json"
            while not decision_path.exists():
                if time.monotonic() >= deadline:
                    raise GateStopped("unconfirmed: Solar review timed out")
                # This pumps Playwright events while waiting for an external file.
                # It is not a fixed sleep used to decide that a UI operation succeeded.
                self.h.page.wait_for_timeout(min(100, max(1, (deadline - time.monotonic()) * 1000)))
            require(time.monotonic() < deadline, "late review decision")
            require(decision_path.stat().st_size <= 131072, "oversized review decision")
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            validate_decision(decision, request, request_hash, folder, hashes, trigger == "failure")
            record.update(status="reviewed", solar_decision=decision["decision"],
                          classification=decision["classification"], decision_sha256=digest(decision_path))
            self.h._recorder.emit("intervention_decision", **record)
            return record, folder, decision
        except Exception as exc:
            record.update(status="stopped", error=str(exc))
            raise GateStopped(str(exc)) from exc
        finally:
            record["review_elapsed_seconds"] = time.monotonic() - start
            self.write(folder / "review-outcome.json", record)

    def checkpoint(self, checkpoint_id):
        require(self.h._active is None, "checkpoint must be outside an action")
        require(all(s["status"] == "matched" for s in self.h.results), "prior step failed")
        matches = [g for g in self.gates if g["id"] == checkpoint_id]
        require(len(matches) == 1, "unplanned checkpoint")
        gate = matches[0]
        require(checkpoint_id not in self.grants and checkpoint_id not in self.consumed, "checkpoint already used")
        require(self.h._next < len(self.h._case_plan["steps"]), "checkpoint after task end")
        require(self.h._case_plan["steps"][self.h._next]["id"] == gate["before_step"], "checkpoint at wrong step")
        current = self.h._observe()
        evaluation = self._independent(checkpoint_id, current)
        record, folder, decision = self._review(
            checkpoint_id, "planned_review", gate["before_step"], current, evaluation
        )
        try:
            if not evaluate_gate(evaluation) or decision["decision"] != "continue":
                raise GateStopped("unconfirmed: independent evaluator or Solar denied checkpoint")
            actual = self.h._observe()
            fresh = self._independent(checkpoint_id, actual)
            self.write(self.h._out / "private-supervision" / folder.name / "recheck.json", fresh)
            if not evaluate_gate(fresh) or state_fingerprint(actual) != state_fingerprint(current):
                raise GateStopped("unconfirmed: reviewed state changed or failed independent recheck")
            self.grants[checkpoint_id] = {
                "fingerprint": state_fingerprint(actual), "before_step": gate["before_step"],
                "record": record, "folder": folder,
            }
            record["status"] = "granted"
            self.h._recorder.emit("checkpoint_granted", checkpoint_id=checkpoint_id, before_step=gate["before_step"])
            return {"checkpoint_id": checkpoint_id, "decision": "continue"}
        except Exception as exc:
            record.update(status="stopped", error=str(exc))
            raise
        finally:
            self.write(folder / "review-outcome.json", record)

    def before_dispatch(self, step_id, current):
        for gate in self.gates:
            if gate["before_step"] != step_id:
                continue
            granted = self.grants.get(gate["id"])
            if not granted or gate["id"] in self.consumed:
                raise GateStopped("unconfirmed: required checkpoint not granted or already consumed")
            fresh = self._independent(gate["id"], current)
            self.write(self.h._out / "private-supervision" / granted["folder"].name / "dispatch-check.json", fresh)
            if not evaluate_gate(fresh) or state_fingerprint(current) != granted["fingerprint"]:
                granted["record"].update(status="stopped", error="State changed before action dispatch")
                self.write(granted["folder"] / "review-outcome.json", granted["record"])
                raise GateStopped("unconfirmed: checkpoint state stale at action dispatch")
            self.consumed.add(gate["id"])
            granted["record"]["status"] = "consumed"
            self.write(granted["folder"] / "review-outcome.json", granted["record"])
            self.h._recorder.emit("checkpoint_consumed", checkpoint_id=gate["id"], before_step=step_id)

    def diagnose_failure(self, error):
        if self.diagnosed or isinstance(error, GateStopped):
            return
        self.diagnosed = True
        current = self.h._observe()
        pending = (self.h._case_plan["steps"][self.h._next]["id"]
                   if self.h._next < len(self.h._case_plan["steps"]) else None)
        evaluation = {"decision": "stop", "checks": [],
                      "public_summary": "Run failed. Diagnose only; no write retry or in-place continuation."}
        try:
            record, folder, _ = self._review("failure", "failure", pending, current, evaluation, str(error))
            record["status"] = "diagnosed_stopped"
            self.write(folder / "review-outcome.json", record)
        except Exception as exc:
            self.h._recorder.emit("failure_review_unavailable", error=str(exc))

    def all_consumed(self):
        return self.consumed == {g["id"] for g in self.gates} and all(
            record["status"] == "consumed" for record in self.records
        )
