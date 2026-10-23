"""Read-only supervision summary, without printing application data or secrets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def inspect_run(run_dir):
    root = Path(run_dir).resolve()
    workspace, private = root / "workspace", root / "private"
    health = _json(private / "gateway-health.json")
    requests = []
    for path in sorted((workspace / "browser-requests").glob("*.status.json")):
        value = _json(path)
        if value:
            requests.append({key: value.get(key) for key in
                ("state", "exit_code", "broker_status", "elapsed_seconds")})
    events = {}
    last_action_time = None
    for path in (private / "broker").glob("call-*/evidence/actions.jsonl"):
        for row in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(row)
            except ValueError:
                continue
            kind = value.get("kind", value.get("event", value.get("type", "unspecified")))
            events[kind] = events.get(kind, 0) + 1
        last_action_time = max(last_action_time or 0, path.stat().st_mtime)
    ready = _json(workspace / "READY.json") or {}
    return {
        "run": root.name,
        "isolation_limited": True,
        "strict_score": None,
        "gateway": None if not health else {"state": health.get("state"),
            "heartbeat_age_seconds": round((time.time_ns() - health["time_ns"]) / 1e9, 2)},
        "stop_present": any((p / "STOP").exists() for p in (root, workspace, private)),
        "requests": requests,
        "event_counts": events,
        "action_journal_age_seconds": None if last_action_time is None else round(time.time() - last_action_time, 2),
        "declared_artifact_revision": ready.get("revision"),
        "declared_artifact_status": ready.get("status"),
        "artifact_claims_are_not_independent_validation": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--watch", type=float, default=0,
                        help="Repeat every 1–60 seconds; default prints once")
    args = parser.parse_args()
    if args.watch and not 1 <= args.watch <= 60:
        parser.error("--watch must be 1–60 seconds")
    try:
        while True:
            print(json.dumps(inspect_run(args.run), ensure_ascii=False), flush=True)
            if not args.watch:
                break
            time.sleep(args.watch)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
