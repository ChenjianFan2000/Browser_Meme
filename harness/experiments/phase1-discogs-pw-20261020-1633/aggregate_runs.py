"""Summarize frozen Harness outputs without deriving any website rules."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNS = (
    "anchor-initial-001",
    "anchor-initial-002",
    "extension-initial-001",
    "anchor-repair-001",
    "extension-repair-001",
    "anchor-repeat-001",
    "extension-repeat-001",
    "anchor-repeat-002",
    "extension-repeat-002",
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(summary):
    return [
        {
            "id": case["id"],
            "status": case["status"],
            "passed": case["passed"],
            "steps": [
                {
                    "id": step["id"],
                    "status": step["status"],
                    "matched_branches": step.get("matched_branches", []),
                }
                for step in case["steps"]
            ],
            "checks": [
                {"id": check["id"], "passed": check["passed"]}
                for check in case.get("independent_checks", [])
            ],
            "baseline_sha256": case.get("setup", {}).get("baseline_sha256"),
            "initial_table_hashes": case.get("setup", {}).get("table_hashes"),
            "browser_version": case.get("browser_version"),
        }
        for case in summary["cases"]
    ]


def build():
    data = {name: read(ROOT / name / "summary.json") for name in RUNS}
    registrations = {name: read(ROOT / name / "registration.json") for name in RUNS}
    repeats = []
    for family in ("anchor", "extension"):
        reference = f"{family}-repair-001"
        for number in (1, 2):
            name = f"{family}-repeat-{number:03d}"
            same_input = (
                registrations[name]["source_and_implementation_hashes"]
                == registrations[reference]["source_and_implementation_hashes"]
            )
            same_result = signature(data[name]) == signature(data[reference])
            repeats.append(
                {
                    "run_id": name,
                    "reference": reference,
                    "same_frozen_inputs": same_input,
                    "same_outcomes_checks_and_initial_state": same_result,
                    "integrity_errors": data[name]["integrity_errors"],
                    "repeatability_check_passed": (
                        same_input and same_result and not data[name]["integrity_errors"]
                    ),
                }
            )
    unique_cases = set()
    for name in ("anchor-repair-001", "extension-repair-001"):
        case_ids = {case["id"] for case in data[name]["cases"]}
        if unique_cases & case_ids:
            raise ValueError("Suites overlap; do not sum unique task denominators.")
        unique_cases.update(case_ids)
    rounds = []
    for title, names in (
        ("first_business_execution", ("anchor-initial-002", "extension-initial-001")),
        ("model_repair_regression", ("anchor-repair-001", "extension-repair-001")),
        ("frozen_replay_1", ("anchor-repeat-001", "extension-repeat-001")),
        ("frozen_replay_2", ("anchor-repeat-002", "extension-repeat-002")),
    ):
        rounds.append(
            {
                "kind": title,
                "runs": list(names),
                "metrics": {
                    key: sum(data[name]["metrics"][key] for name in names)
                    for key in (
                        "case_denominator",
                        "passed_cases",
                        "step_denominator",
                        "matched_steps",
                        "ui_actions_dispatched",
                        "ui_actions_completed",
                        "elapsed_seconds",
                    )
                },
                "all_goals_accepted": all(data[name]["activation_allowed"] for name in names),
            }
        )
    return {
        "experiment_id": ROOT.name,
        "scope": "phase1 source-visible development, repair and frozen replay",
        "unique_task_denominator": len(unique_cases),
        "model_tokens": None,
        "model_cost": None,
        "measurement_limits": [
            "No held-out generalization, phase2 learning or official benchmark claim.",
            "No strict speed comparison; elapsed values describe these executions only.",
            "Source coverage, branch prediction and independent task completion are separate.",
            "Stable failure remains failure; repeatability never waives a goal.",
        ],
        "runs": [
            {
                "run_id": name,
                "revision": data[name]["revision"],
                "measurement_status": data[name]["measurement_status"],
                "metrics": data[name]["metrics"],
                "regressions": data[name]["regressions"],
                "integrity_errors": data[name]["integrity_errors"],
                "activation_allowed": data[name]["activation_allowed"],
                "summary_sha256": digest(ROOT / name / "summary.json"),
                "registration_sha256": digest(ROOT / name / "registration.json"),
            }
            for name in RUNS
        ],
        "rounds": rounds,
        "repeatability": repeats,
        "all_frozen_repeats_consistent": all(
            item["repeatability_check_passed"] for item in repeats
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build()
    with args.out.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
        target.write("\n")
    print(json.dumps(
        {
            "output": str(args.out),
            "unique_task_denominator": report["unique_task_denominator"],
            "all_frozen_repeats_consistent": report["all_frozen_repeats_consistent"],
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
