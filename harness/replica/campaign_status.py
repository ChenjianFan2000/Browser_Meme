"""Read-only, enum-only status for six preregistered replica run directories."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

SCHEMA = "replica-script-continuity/v3"
MODE = "playwright_script_continuity"
INPUT_SCHEMA = "replica-campaign-status-input/v1"
CHECKPOINT = re.compile(r"(?:state0|final(?:-released)?|step-[0-9]{4,8}|capture_timeout|post_cleanup)")
LAYERS = set("public_dom playwright_semantics business action_identity action_error_free stability capture_stability_unconfirmed needs_reading playwright_semantics_unconfirmed runtime_terminated resource_limit cleanup_failure incomplete_execution action_sequence_length_mismatch coordinator_stop wall_time_exhausted no_checkpoint_progress memory_guard disk_guard".split())
COMPLETION = set("completed terminated unconfirmed needs_reading stopped unconfirmed_no_business_actions".split())


def read(path):
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, RecursionError):
        return {}


def flag(value):
    return value if type(value) is bool else None


def number(value):
    return value if type(value) in (int, float) and 0 <= value <= 1e12 else None


def enum(value, choices):
    return value if isinstance(value, str) and value in choices else "unknown"


def point(value):
    return value if isinstance(value, str) and CHECKPOINT.fullmatch(value) else "unknown"


def mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0


def run_status(root, cell):
    directory = root / cell["result_directory"]
    result_path, status_path = directory / "result.json", directory / "status.json"
    final = read(result_path)
    heartbeat = read(status_path)
    failure = final.get("first_failure")
    failure = failure if isinstance(failure, dict) else {}
    paths = [p for p in (directory / "comparisons").glob("*/step-result.json") if point(p.parent.name) != "unknown"]
    latest_path = max(paths, key=mtime, default=None)
    checkpoint = point(failure.get("checkpoint") or heartbeat.get("checkpoint"))
    if checkpoint == "unknown" and latest_path:
        checkpoint = latest_path.parent.name
    comparison_path = directory / "comparisons" / checkpoint.replace("-released", "") / "step-result.json"
    comparison = read(comparison_path) if checkpoint != "unknown" else {}
    known = final.get("schema") == SCHEMA and final.get("mode") == MODE
    qualified = known and not failure and final.get("completion_status") == "completed" and all(final.get(k) is True for k in ("script_continuity_pass", "state0_compared", "final_compared", "action_identity_match")) and final.get("business_verdict") == "pass" and not any(final.get(k) is False for k in ("primary_pass", "public_dom_match", "playwright_semantics_match"))
    timestamp = max(mtime(result_path), mtime(status_path), mtime(latest_path) if latest_path else 0)
    summary = {"schema": enum(final.get("schema"), {SCHEMA}), "mode": enum(final.get("mode"), {MODE}),
               "completion_status": enum(final.get("completion_status"), COMPLETION),
               "script_continuity_pass": flag(final.get("script_continuity_pass")),
               "full_ax_match": flag(final.get("full_ax_match")),
               "business_verdict": enum(final.get("business_verdict"), {"pass", "fail", "unconfirmed"}),
               "action_identity_match": flag(final.get("action_identity_match")),
               "state0_compared": flag(final.get("state0_compared")), "final_compared": flag(final.get("final_compared")),
               "elapsed_seconds": number(final.get("elapsed_seconds"))}
    return {"flow": cell["flow"], "strategy": cell["strategy"],
            "run_status": "final" if result_path.exists() else "running" if directory.exists() else "not_run",
            "latest": {"checkpoint": checkpoint, "pass": flag(comparison.get("script_continuity_pass")) if comparison.get("schema") == SCHEMA and comparison.get("mode") == MODE else None,
                       "failure_layer": enum(failure.get("layer") or comparison.get("first_failure_layer"), LAYERS) if failure.get("layer") or comparison.get("first_failure_layer") else None,
                       "age_seconds": round(max(0, time.time() - timestamp), 1) if timestamp else None},
            "final": summary if result_path.exists() else None, "qualified_pass": qualified,
            "cleanup_present": all((directory / lane / "cleanup.json").is_file() for lane in ("source", "replica"))}


def campaign(path):
    config = read(path)
    if config.get("schema") != INPUT_SCHEMA or not all(isinstance(config.get(k), str) for k in ("repo_root", "profile", "candidate")):
        raise ValueError
    root = Path(config["repo_root"]).resolve()
    cells = config.get("cells")
    if not isinstance(cells, list) or len(cells) != 6:
        raise ValueError
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {"flow", "strategy", "result_directory"}:
            raise ValueError
        if not all(isinstance(cell[k], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cell[k]) for k in ("flow", "strategy")):
            raise ValueError
        (root / cell["result_directory"]).resolve().relative_to(root)
    if len({(c["flow"], c["strategy"]) for c in cells}) != 6 or len({(root / c["result_directory"]).resolve() for c in cells}) != 6:
        raise ValueError
    return config, root, cells


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--watch", type=float, default=0, metavar="SECONDS")
    parser.add_argument("--watch10", dest="watch", action="store_const", const=10)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        config, root, cells = campaign(args.campaign)
        if not math.isfinite(args.watch) or args.watch < 0 or 0 < args.watch < 1:
            raise ValueError
        if args.out:
            target = args.out.resolve()
            if target.parent != root / "work/replica-status" or target.suffix != ".json" or target.name.upper() == "PROGRESS.JSON" or target in {args.campaign.resolve(), (root / config["profile"]).resolve()} or any(target.is_relative_to((root / c["result_directory"]).resolve()) for c in cells):
                raise ValueError
            target.parent.mkdir(parents=True, exist_ok=True)
        while True:
            rows = [run_status(root, cell) for cell in cells]
            value = {"schema": "replica-campaign-status/v1", "repo_root": str(root), "profile": config["profile"], "candidate": config["candidate"], "status_basis": "artifact_existence_no_liveness_check", "runs": rows}
            text = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
            if args.out:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=".campaign-status-", delete=False) as stream:
                    stream.write(text)
                os.replace(stream.name, target)
            print(text, end="", flush=True)
            if not args.watch:
                break
            time.sleep(args.watch)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, TypeError):
        parser.exit(2, "campaign_status: invalid_or_unreadable_input_or_output\n")


if __name__ == "__main__":
    main()
