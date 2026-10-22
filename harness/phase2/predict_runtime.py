"""Run an immutable learner-owned predictor inside an offline Linux namespace."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    model_path = Path(job["model_path"]).resolve(strict=True)
    sys.path.insert(0, str(model_path.parent))
    spec = importlib.util.spec_from_file_location("frozen_behavior_model", model_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = module.predict(job["observation"], job["intent"])
    with (Path(args.job).parent / "prediction.json").open("x") as out:
        json.dump(result, out, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    main()
