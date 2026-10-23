"""Explicit offline render and single-source execution entry points."""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from .runner import run_source
from .validator import render


def read(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    renderer = commands.add_parser("render", help="Export a symbolic component tree for supplied external inputs")
    renderer.add_argument("--contracts", required=True)
    renderer.add_argument("--ref", required=True)
    renderer.add_argument("--inputs", required=True)
    renderer.add_argument("--branch")
    renderer.add_argument("--out", required=True)
    runner = commands.add_parser("run", help="Execute one native Playwright source with live independent gates")
    runner.add_argument("--config", required=True)
    args = parser.parse_args()
    if args.command == "render":
        bundle = read(args.contracts)
        result = render(bundle["contracts"][args.ref], read(args.inputs), branch=args.branch)
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"schema": result["schema"], "output": str(destination)}))
        return 0
    config = read(args.config)
    adapter = config.pop("oracle", None)
    oracle = None
    if adapter is not None:
        module = importlib.import_module(adapter["module"])
        factory = getattr(module, adapter["factory"])
        oracle = factory(**adapter.get("kwargs", {}))
    if isinstance(config.get("source_plan"), str):
        config["source_plan"] = read(config["source_plan"])
    result = run_source(**config, oracle=oracle)
    print(json.dumps({key: result[key] for key in ("schema", "primary_pass", "reason", "checked_actions", "first_failure")}))
    return 0 if result["primary_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
