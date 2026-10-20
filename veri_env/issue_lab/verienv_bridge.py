"""Real VeriEnv judge integration, independent of any learned transition model."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
JUDGE_PATH = ROOT / 'external/VeriEnv-main/BrowserGym/browsergym/experiments/src/browsergym/experiments/verienv/judge_dsl.py'


@lru_cache(maxsize=1)
def native_judge():
    spec = importlib.util.spec_from_file_location('issue_lab_native_verienv_judge', JUDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fingerprint(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def judge_state(predicted_canonical, expected_canonical):
    """Protect strict semantics from upstream string normalization using SHA256.

    The expected state is produced independently by the evaluator, not by the
    candidate model. The native DSL evaluates an ordinary JSON exact_match check.
    """
    module = native_judge()
    judge_spec = module.parse_judge_spec({'eval_type': 'rinfo', 'parse': 'json', 'checks': [
        {'op': 'exact_match', 'path': 'state_sha256', 'expected': fingerprint(expected_canonical)}]})
    result = module.eval_rinfo_checks(judge_spec.checks,
        answer_text=json.dumps({'state_sha256': fingerprint(predicted_canonical)}),
        answer_obj=None, parse_mode=judge_spec.parse_mode)
    return result.to_dict()
