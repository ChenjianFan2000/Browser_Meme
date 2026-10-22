"""Index immutable phase-two packages for later phase-three registration."""
from __future__ import annotations

import argparse
import json

from .records import sha256, verify_manifest, write_new_json
from .run_learning import EXPERIMENT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff-id", required=True)
    parser.add_argument("--learning-review", required=True)
    parser.add_argument("--evaluation-report", required=True)
    parser.add_argument("--independent-review", required=True)
    args = parser.parse_args()
    schedule = read(EXPERIMENT / "FORMAL_SCHEDULE.json")
    references = {}
    for key, relative in (("learning_review", args.learning_review),
                          ("evaluation_report", args.evaluation_report),
                          ("independent_review", args.independent_review)):
        path = (EXPERIMENT / relative).resolve(strict=True)
        path.relative_to(EXPERIMENT.resolve())
        references[key] = {"path": relative, "sha256": sha256(path), "visibility": "management_only_for_first_frozen_combinations"}
    packages = []
    for worker in schedule["workers"]:
        for condition in worker["conditions"]:
            run_id = condition.lower() + "-seed-" + str(worker["seed"])
            root = EXPERIMENT / "runs" / run_id
            manifest = root / "learning-manifest.json"
            if verify_manifest(root, read(manifest)["files"]):
                raise ValueError("learning package changed before handoff")
            ready = read(root / "workspace/READY.json")
            revision = root / "workspace" / ready["revision_directory"]
            files = {str(path.relative_to(root / "workspace")).replace("\\", "/"): sha256(path)
                     for path in revision.rglob("*") if path.is_file()}
            files["READY.json"] = sha256(root / "workspace/READY.json")
            packages.append({"run_id": run_id, "condition": condition, "seed": worker["seed"],
                             "workspace": str((root / "workspace").relative_to(EXPERIMENT)).replace("\\", "/"),
                             "revision": ready["revision_directory"], "learning_manifest_sha256": sha256(manifest),
                             "allowed_frozen_artifact_hashes": files,
                             "limitations_source": "READY.json and the frozen revision coverage.json",
                             "has_executable_predictor": condition == "A"})
    result = {"kind": "phase_three_handoff_without_phase_three_execution", "phase_two_protocol": schedule["protocol"],
              "packages": packages, "management_reviews": references,
              "first_frozen_combination_rules": [
                  "Register website/dependency/account/observation/action scope and equivalent initial states again.",
                  "Use native Playwright through the accepted generic Harness and independent website checks.",
                  "Keep workflow templates disjoint and independently audit them against actual exploration evidence.",
                  "Do not provide phase-two test answers, private state, evaluator source or other-case feedback to first frozen combination contexts.",
                  "Do not modify the frozen package; temporary task scripts and same-task supervision remain a separately registered allowance.",
                  "Freeze first-attempt predictions before business actions and preserve failures, refusals, unknowns and timeouts.",
                  "Put online repairs in new parent-linked versions and separate adaptation scores from original frozen scores.",
                  "Report operation coverage, strict speed comparisons and combination evaluation separately."
              ], "third_stage_started": False, "official_benchmark": False}
    destination = EXPERIMENT / "handoff" / (args.handoff_id + ".json")
    write_new_json(destination, result)
    print(json.dumps({"handoff": str(destination), "packages": len(packages), "third_stage_started": False}))


if __name__ == "__main__":
    main()
