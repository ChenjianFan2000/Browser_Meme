"""Offline upstream-component execution audit, never a paper-method score.

Run ``python -m issue_lab.upstream_audit`` to replay synthetic public fixtures.
No learner/model files, private evaluation data, network, or model API are used.
The native_patchworld_validate hook only reads the code path explicitly supplied
by its caller. It adapts predict(state_dict, action_dict) to upstream interfaces.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
import types
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "external"
sys.dont_write_bytecode = True


def source_record(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}


def load_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses consult their defining module
    spec.loader.exec_module(module)
    return module


def extract(path: Path, names: list[str], injected: dict | None = None,
            class_methods: dict[str, list[str]] | None = None) -> tuple[dict, dict]:
    """Execute unchanged selected AST definitions; omit all original imports/top-level calls."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    chosen, ranges = [], []
    for node in tree.body:
        node_names = ([node.name] if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                      else [target.id for target in node.targets if isinstance(target, ast.Name)]
                      if isinstance(node, ast.Assign) else [])
        if not set(node_names).intersection(names):
            continue
        ranges.append({"names": node_names, "start_line": node.lineno, "end_line": node.end_lineno})
        if isinstance(node, ast.ClassDef) and class_methods and node.name in class_methods:
            keep = class_methods[node.name]
            node.body = [child for child in node.body
                         if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) or child.name in keep]
            ranges[-1]["kept_methods"] = keep
        chosen.append(node)
    found = {name for record in ranges for name in record["names"]}
    if set(names) - found:
        raise ValueError(f"Definitions missing in {path}: {set(names) - found}")
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    namespace = {"__name__": "upstream_extracted", "__file__": str(path), **(injected or {})}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *chosen], type_ignores=[])),
                 str(path), "exec"), namespace)
    return namespace, {**source_record(path), "execution": "selected_original_AST", "ranges": ranges}


@contextlib.contextmanager
def upstream_path(path: Path):
    sys.path.insert(0, str(path))
    try:
        yield
    finally:
        sys.path.remove(str(path))


def _json_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)


def _patchworld_components():
    with upstream_path(EXTERNAL / "PatchWorld"):
        validator = importlib.import_module("patchworld.worldmodel_validator")
        data = importlib.import_module("patchworld.worldmodel_data")
        evaluator = importlib.import_module("patchworld.worldmodel_evaluator")
    return validator, data, evaluator


def _patchworld_wrapper(predict_code: str) -> str:
    # This is only an interface adapter. Neither corrections nor transitions are
    # learned here. predict must supply all transition semantics itself.
    return ("import json\nfrom copy import deepcopy\n"
            "from patchworld.worldmodel_base import BaseWorldModel\n"
            f"_namespace = {{}}\nexec({ascii(predict_code)}, _namespace)\n"
            "_predict = _namespace['predict']\n"
            "_audit_predictions = []\n"
            "class JsonIssueWorldModel(BaseWorldModel):\n"
            "    def parse_observation(self, text): return json.loads(text)\n"
            "    def extract_valid_action_forms(self): return {}\n"
            "    def correct_belief(self, prior, text): return self.parse_observation(text)\n"
            "    def predict_belief(self, belief, action):\n"
            "        prediction = _predict(deepcopy(belief), json.loads(action))\n"
            "        _audit_predictions.append({'state':deepcopy(belief), 'action':json.loads(action), 'prediction':deepcopy(prediction)})\n"
            "        return prediction\n"
            "    def readout_observation(self, belief, action=''):\n"
            "        return json.dumps(belief, sort_keys=True, ensure_ascii=False)\n")


def _native_patchworld_validate_code(predict_code: str, trajectories: list) -> dict:
    validator, data, evaluator = _patchworld_components()
    native = []
    if trajectories and isinstance(trajectories[0], dict) and "transitions" not in trajectories[0]:
        trajectories = [{"transitions": trajectories}]
    for index, trajectory in enumerate(trajectories):
        if isinstance(trajectory, data.Trajectory):
            native.append(trajectory)
            continue
        steps = trajectory["transitions"] if isinstance(trajectory, dict) else trajectory
        transitions = []
        for step in steps:
            before = step.get("state", step.get("observation"))
            after = step.get("next_state", step.get("next_observation", step.get("state_next")))
            if before is None or after is None or "action" not in step:
                raise ValueError("Each transition requires state/observation, action, next_state/next_observation")
            transitions.append(data.Transition(_json_text(before), _json_text(step["action"]),
                                               _json_text(after), float(step.get("reward", 0)),
                                               bool(step.get("done", False))))
        native.append(data.Trajectory(transitions, "issue_lab", str(index), index, 0,
                                      "caller_supplied", False, 0.0))
    code = _patchworld_wrapper(predict_code)
    # Original loader writes a temporary Python file. Track and delete only those
    # files it created during this call; leave upstream source untouched.
    paths, modules = [], []
    original_loader = validator._load_module_from_code
    def tracking_loader(generated_code):
        module = original_loader(generated_code)
        paths.append(Path(module.__file__))
        modules.append(module)
        return module
    validator._load_module_from_code = tracking_loader
    try:
        with upstream_path(EXTERNAL / "PatchWorld"):
            errors = validator.validate_model(code, native, max_trajectories=len(native), method_timeout_s=0)
    finally:
        validator._load_module_from_code = original_loader
        for path in paths:
            path.unlink(missing_ok=True)
    def canonical(value):
        return json.dumps(json.loads(value) if isinstance(value, str) else value,
                          sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    expected = {(canonical(step.observation), canonical(step.action)): canonical(step.next_observation)
                for trajectory in native for step in trajectory.transitions}
    strict_errors, strict_checks = [], 0
    for module in modules:
        for item in getattr(module, "_audit_predictions", []):
            strict_checks += 1
            key = (canonical(item["state"]), canonical(item["action"]))
            try:
                actual = canonical(item["prediction"])
            except (TypeError, ValueError) as exc:
                strict_errors.append({"error_type": "invalid_json_prediction", "action": item["action"], "got": str(exc)})
                continue
            if expected.get(key) != actual:
                strict_errors.append({"error_type": "strict_json_mismatch", "action": item["action"],
                                      "expected": expected.get(key), "got": actual})
    return {"validator": "patchworld.worldmodel_validator.validate_model", "errors": errors,
            "strict_errors": strict_errors, "strict_prediction_checks": strict_checks,
            "passed": not errors and not strict_errors and (strict_checks > 0 or not expected), "trajectories": len(native),
            "transitions": sum(len(t.transitions) for t in native),
            "adapter": "JSON parse/correct/readout; predict provides transition; no method timeout"}


def native_patchworld_validate(code_path: str | Path, trajectories: list) -> dict:
    """Run ORIGINAL PatchWorld validator on caller-authorized predict source.

    trajectories may be a flat list of {state,action,next_state}, a list of
    {transitions:[...]}, or upstream Trajectory objects. Observation/action dicts
    are JSON encoded. The caller supplies public learning trajectories; this hook
    does not locate or open any model or evaluation files on its own.
    Windows cannot enforce upstream Unix signal timeouts; run untrusted or
    potentially nonterminating code in a separately timed subprocess.
    """
    path = Path(code_path)
    return _native_patchworld_validate_code(path.read_text(encoding="utf-8-sig"), trajectories)


def fixture():
    state = {"issues": [{"id": 17, "title": "Synthetic fixture", "status": "open", "labels": [],
                         "blocked": False, "priority": 2, "comments": []}],
             "filter": {"status": "all", "label": ""}, "sort": "asc", "selected": [],
             "role": "editor", "feedback": {"ok": True, "code": "ok"}, "visible_ids": [17]}
    next_state = copy.deepcopy(state)
    next_state["sort"] = "desc"
    return state, {"type": "sort", "direction": "desc"}, next_state


class RecordingClient:
    """No API implementation: records exact calls and returns declared fixtures."""
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.chat = types.SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=next(self.responses)))])


class QuietLogger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def audit_verienv():
    path = EXTERNAL / "VeriEnv-main/BrowserGym/browsergym/experiments/src/browsergym/experiments/verienv/judge_dsl.py"
    module = load_file(path, "audit_verienv_judge")
    spec = module.parse_judge_spec({"parse": "json", "checks": [
        {"op": "exact_match", "path": "sort", "expected": "desc"},
        {"op": "exact_match", "path": "issues.0.status", "expected": "open"}]})
    state, action, after = fixture()
    passed = module.eval_rinfo_checks(spec.checks, answer_text=_json_text(after), answer_obj=None, parse_mode=spec.parse_mode)
    failed = module.eval_rinfo_checks(spec.checks, answer_text=_json_text(state), answer_obj=None, parse_mode=spec.parse_mode)
    assert passed.passed and not failed.passed
    return {"sources": [source_record(path)], "executed": "full unmodified judge_dsl module: parse_judge_spec + eval_rinfo_checks",
            "evidence": {"spec": spec.to_dict(), "positive": passed.to_dict(), "negative": failed.to_dict()},
            "substitutions": [], "scope": "structured task judgment only, not browser/environment synthesis"}


def audit_patchworld():
    state, action, after = fixture()
    trajectories = [{"state": state, "action": action, "next_state": after}]
    good = "def predict(state, action):\n    state['sort'] = action['direction']\n    return state\n"
    bad = "def predict(state, action):\n    return state\n"
    positive = _native_patchworld_validate_code(good, trajectories)
    negative = _native_patchworld_validate_code(bad, trajectories)
    casing = _native_patchworld_validate_code(good.replace("    return state", "    state['issues'][0]['title'] = state['issues'][0]['title'].upper()\n    return state"), trajectories)
    non_json = _native_patchworld_validate_code("def predict(s,a):\n return {'bad':{1,2}}", trajectories)
    with tempfile.TemporaryDirectory(prefix="upstream-audit-hook-") as directory:
        path = Path(directory) / "synthetic_predict.py"
        path.write_text(good, encoding="utf-8")
        public_hook = native_patchworld_validate(path, trajectories)
    assert positive["passed"] and not negative["passed"]
    assert not casing["errors"] and casing["strict_errors"] and not casing["passed"]
    assert not non_json["passed"] and any(error["error_type"] == "invalid_json_prediction" for error in non_json["strict_errors"])
    assert public_hook["passed"] and public_hook["strict_prediction_checks"] == 2
    return {"sources": [source_record(EXTERNAL / "PatchWorld/patchworld" / filename) for filename in
                        ("worldmodel_base.py", "worldmodel_data.py", "worldmodel_validator.py", "worldmodel_evaluator.py")],
            "executed": "full original BaseWorldModel interface + validate_model + compare_parsed_observations",
            "evidence": {"positive": positive, "negative": negative, "normalization_false_positive_caught": casing,
                         "non_json_prediction_rejected": non_json, "public_code_path_hook": public_hook},
            "substitutions": ["new JSON adapter subclass; no latent-state claim for issue_lab",
                              "method_timeout_s=0; upstream signal timeout unavailable on Windows",
                              "loader wrapper tracks/deletes upstream-created temporary modules"],
            "scope": "original validator replays hand-authored adapter fixtures; not PatchWorld induction/repair"}


def audit_worldcoder():
    base_path = EXTERNAL / "WorldCoder/worldcoder/envs/base.py"
    bases = load_file(base_path, "audit_worldcoder_bases")
    eval_path = EXTERNAL / "WorldCoder/worldcoder/utils/eval_code.py"
    original = load_file(eval_path, "audit_worldcoder_eval_code")
    native_result = original.eval_code("result = 1 + 1")
    def portable_exec(code, timeout=3, return_exec_globals=False, exec_globals=None):
        namespace = {} if exec_globals is None else exec_globals
        try:
            exec(code, namespace)
            return namespace if return_exec_globals else "passed"
        except BaseException as exc:
            return "failed: " + repr(exc)
    evaluator_path = EXTERNAL / "WorldCoder/worldcoder/agent/synthesizer/evaluator.py"
    namespace, record = extract(evaluator_path, ["_Evaluator", "TransitEvaluator"],
                                {"copy": copy, "hashlib": hashlib, "eval_code": portable_exec,
                                 "_State": bases._State, "_Action": bases._Action})
    class JsonState(bases._State):
        def __init__(self, value): self.value = copy.deepcopy(value)
        def to_hashable(self): return _json_text(self.value)
        def to_pyrunnable(self, **kwargs): return copy.deepcopy(self.value)
        @classmethod
        def check_valid_pyrunnable(cls, value): return True if isinstance(value, dict) else "not a JSON state"
        @classmethod
        def from_pyrunnable(cls, value): return cls(value)
    class JsonAction(bases._Action):
        def __init__(self, value): self.value = copy.deepcopy(value)
        def to_pyrunnable(self, **kwargs): return copy.deepcopy(self.value)
    state, action, after = fixture()
    experiences = {0: {"state": JsonState(state), "action": JsonAction(action), "state_next": JsonState(after)}}
    evaluator = namespace["TransitEvaluator"]()
    positive = evaluator("def transition(s,a):\n s['sort']=a['direction']\n return s", experiences)
    negative = evaluator("def transition(s,a):\n return s", experiences)
    assert positive["success_ratio"] == 1 and negative["success_ratio"] == 0
    return {"sources": [source_record(base_path), source_record(eval_path), record],
            "executed": "original _State/_Action + extracted TransitEvaluator selection and experience evaluation",
            "evidence": {"original_eval_code_result": native_result,
                         "adapted_positive_ratio": positive["success_ratio"], "adapted_negative_ratio": negative["success_ratio"]},
            "substitutions": ["JSON subclasses of original _State/_Action",
                              "eval_code replaced with portable exec without timeout; original fails on Windows signal.setitimer",
                              "imports of planner, WorldModel, caches and numpy omitted by AST selection"],
            "scope": "transition-evaluator core, not original synthesis/planning loop"}


def audit_gif():
    root = EXTERNAL / "code-world-models/src"
    helpers, helper_record = extract(root / "code_helpers.py", ["extract_code"], {"re": re})
    logger = QuietLogger()
    parser, parser_record = extract(root / "mcts/gif_mcts/parser.py", ["Parser"],
                                    {"DEFAULT_LOGGER": logger, "code_helpers": types.SimpleNamespace(**helpers)})
    nodes, node_record = extract(root / "mcts/gif_mcts/code_state_node.py", ["CodeStateNode"], {"DEFAULT_LOGGER": logger})
    completion = "## Error explanation\nThe direction was ignored.\n## Correct code\n```python\ndef predict(s,a):\n s['sort']=a['direction']\n return s\n```"
    parsed = parser["Parser"]().parse(completion, "", 10, "fix")
    node = nodes["CodeStateNode"]()
    node.expand(parsed[0], 0, False, parsed[3], parsed[4], parsed[1], parsed[2], "fix", {"bug": True})
    node.visit_count = 2
    assert list(node.children) == ["f1"]
    assert node.value() == .495
    return {"sources": [helper_record, parser_record, node_record],
            "executed": "Parser.parse(fix) and CodeStateNode.expand/value; bug branch produces fix child",
            "evidence": {"parsed": parsed, "child_actions": list(node.children), "value": node.value()},
            "substitutions": ["mloggers replaced by no-op QuietLogger; original imports/path mutation omitted"],
            "scope": "code-search parser/tree bookkeeping, not full GIF-MCTS search or learned world model"}


def audit_poe():
    import numpy as np
    import scipy
    import scipy.special
    import random
    utils, utils_record = extract(EXTERNAL / "poe-world/classes/utils.py", ["logsumexp", "exp_normalize"], {"np": np, "scipy": scipy})
    helper, helper_record = extract(EXTERNAL / "poe-world/classes/helper.py", ["RandomValues", "combine_random_values"],
                                    {"np": np, "random": random, "logsumexp": utils["logsumexp"],
                                     "exp_normalize": utils["exp_normalize"], "LOG_IMPOSSIBLE_VALUE": -1000})
    values = helper["RandomValues"]
    combined = helper["combine_random_values"]([values([0, 1], np.log([.8, .2])),
                                                 values([0, 1], np.log([.4, .6]))], np.array([.5, .5]), False)
    probabilities = [float(np.exp(combined.evaluate_logprobs(i))) for i in (0, 1)]
    assert abs(sum(probabilities) - 1) < 1e-10 and combined.get_max_prob_value() == 0
    return {"sources": [utils_record, helper_record],
            "executed": "original NumPy RandomValues logprob and weighted logscore expert composition",
            "evidence": {"expert_probabilities": [[.8, .2], [.4, .6]], "weights": [.5, .5],
                         "composed_probabilities": probabilities, "argmax": int(combined.get_max_prob_value())},
            "substitutions": ["AST excludes pygame/torch/game imports; real numpy and scipy used",
                              "CPU non-Torch branch only; original LOG_IMPOSSIBLE_VALUE=-1000 supplied"],
            "scope": "probability composition kernel, not ObjTypeModel learning or game policy"}


def audit_wma():
    constants, constant_record = extract(EXTERNAL / "WMA-Agents/browser_env/constants.py",
                                         ["PLAYWRIGHT_ACTIONS", "PLAYWRIGHT_LOCATORS"])
    namespace, record = extract(EXTERNAL / "WMA-Agents/browser_env/actions.py", ["parse_playwright_code"],
                                {"ast": ast, "re": re, "ParsedPlaywrightCode": dict,
                                 **{k: constants[k] for k in ("PLAYWRIGHT_ACTIONS", "PLAYWRIGHT_LOCATORS")}})
    parsed = namespace["parse_playwright_code"]('page.get_by_role("button", name="Close selected").click()')
    invalid = ""
    try:
        namespace["parse_playwright_code"]('page.nonexistent("x").click()')
    except ValueError as exc:
        invalid = str(exc)
    assert len(parsed) == 2 and invalid
    return {"sources": [constant_record, record], "executed": "original parse_playwright_code valid and invalid chained actions",
            "evidence": {"parsed": parsed, "invalid_rejected": invalid},
            "substitutions": ["ParsedPlaywrightCode TypedDict runtime constructor replaced by dict",
                              "Playwright/gymnasium/browser processor imports omitted; locator/action constants unchanged"],
            "scope": "action syntax parsing only; no WMA prediction, policy, or browser execution"}


def audit_webdreamer():
    # Exact type comparison uses anthropic.Anthropic; this marker has no API methods
    # and forces the original OpenAI-client branch for the RecordingClient.
    namespace, record = extract(EXTERNAL / "WebDreamer/world_model.py", ["WebWorldModel", "parse_proposed_action"],
                                {"re": re, "anthropic": types.SimpleNamespace(Anthropic=type("UnavailableAnthropic", (), {}))})
    responses = ["State changes: fixture A", "click Close selected", "State changes: fixture B"]
    client = RecordingClient(responses)
    model = namespace["WebWorldModel"](client)
    output = model.multiple_step_change_prediction("data:image/png;base64,FIXTURE_NOT_A_REAL_IMAGE", "unused", "Synthetic audit task",
                                                    "click Select all visible", k=1)
    assert len(client.calls) == 3 and all(item in output for item in responses)
    assert "fixture A" in json.dumps(client.calls[1]) and "fixture A" in json.dumps(client.calls[2])
    return {"sources": [record], "executed": "original WebWorldModel.multiple_step_change_prediction k=1 and its three prompt/client paths",
            "evidence": {"calls": client.calls, "output": output, "response_source": "declared synthetic RecordingClient fixtures"},
            "substitutions": ["RecordingClient replaces external OpenAI model service; no API call",
                              "anthropic.Anthropic type marker only; no Anthropic execution",
                              "screenshot is an explicitly invalid image sentinel, since no VLM is called"],
            "scope": "prompt construction and imagination control flow; no prediction accuracy evidence"}


def audit_webevolver():
    path = EXTERNAL / "SelfEvolvingAgent/WebEvolver/data/get_world_model_sft_from_trajectory.py"
    # Match the upstream script's declared LLAMA_VERSION without changing process env.
    namespace, record = extract(path, ["extract_info_from_action"],
                                {"re": re, "os": types.SimpleNamespace(environ={"LLAMA_VERSION": "3.3"})})
    results = {text: namespace["extract_info_from_action"](text)
               for text in ("click [17]", "type [21] [reviewed] press_enter_after=1", "stop [done]")}
    assert results["click [17]"][:2] == ("click", "17")
    return {"sources": [record], "executed": "original data-construction action parser for click/type/stop",
            "evidence": results,
            "substitutions": ["script LLAMA_VERSION=3.3 exposed in isolated environ object",
                              "pandas/requests/cognitive_kernel/evaluator imports and top-level script work omitted"],
            "scope": "data/action interface only; no self-evolution training or world-model inference"}


def audit_webworld():
    base = load_file(EXTERNAL / "WebWorld/core/tasks/base_task.py", "audit_webworld_base")
    methods = ["generate_prompt", "_get_task_suffix", "_is_web2nal_task", "evaluate"]
    namespace, record = extract(EXTERNAL / "WebWorld/core/tasks/web_wm.py", ["WebWorldModelTask"],
                                {"BaseTask": base.BaseTask}, {"WebWorldModelTask": methods})
    # Skip dataset/config loader: supply exactly one public synthetic sample.
    task = namespace["WebWorldModelTask"].__new__(namespace["WebWorldModelTask"])
    state, action, after = fixture()
    task.task_path = "WEB_WORLD_MODEL_EVALUATION/base"
    task.samples_map = {"audit": {"observation": _json_text(state), "action": _json_text(action),
                                  "next_observation": "EXPECTED_SENTINEL_NOT_IN_PROMPT"}}
    prompt, metadata = task.generate_prompt(sample_id="audit")
    assert "EXPECTED_SENTINEL_NOT_IN_PROMPT" not in prompt
    assert metadata["ground_truth_next_observation"] == "EXPECTED_SENTINEL_NOT_IN_PROMPT"
    return {"sources": [source_record(EXTERNAL / "WebWorld/core/tasks/base_task.py"), record],
            "executed": "original generate_prompt single-step branch using original BaseTask parent",
            "evidence": {"prompt": prompt, "metadata": metadata, "ground_truth_excluded_from_prompt": True},
            "substitutions": ["constructor/dataset/config loading bypassed via __new__; synthetic samples_map supplied",
                              "only listed original class methods retained; evaluator is not invoked"],
            "scope": "benchmark input prompt interface; no judge model or prediction model execution"}


def audit_agent2world():
    path = EXTERNAL / "agent2world/src/agentic_world_model/utils/handle_response.py"
    module = load_file(path, "audit_agent2world_response")
    payload = module.extract_payload_from_response('<final>```json\n{"sort":"desc"}\n```</final>')
    assert payload == {"sort": "desc"}
    candidate_path = EXTERNAL / "agent2world/src/agentic_world_model/utils/best_code_candidate.py"
    namespace, record = extract(candidate_path, ["select_best_code_candidate"], {"logger": QuietLogger()})
    chosen = namespace["select_best_code_candidate"]([
        {"code": "synthetic A", "pass_rate": .25, "turn": 1},
        {"code": "synthetic B", "pass_rate": .75, "turn": 2}])
    assert chosen["code"] == "synthetic B"
    return {"sources": [source_record(path), record], "executed": "full original response extraction plus original best-candidate rank function",
            "evidence": {"extracted_payload": payload, "selected_candidate": chosen},
            "substitutions": ["candidate selector logger is QuietLogger; type-only imports omitted",
                              "response parser optional yaml/pydantic imports are real installed packages"],
            "scope": "response parsing and candidate ranking, not agentic code generation, self-consistency, sandbox or training"}


def audit_code2world():
    path = EXTERNAL / "Code2World/android_world/agents/qwen_model.py"
    calls = {"checkpoint_requests": [], "processor_calls": [], "generate_calls": [], "saved_html": [], "render_requests": []}
    html = '<!DOCTYPE html><html><body><div id="render-target">Synthetic result</div></body></html>'
    class Batch(dict):
        def __init__(self):
            super().__init__(input_ids=[[7, 8]])
            self.input_ids = self["input_ids"]
        def to(self, device):
            calls["device"] = device
            return self
    class Processor:
        @classmethod
        def from_pretrained(cls, name, **kwargs):
            calls["checkpoint_requests"].append({"kind": "processor", "name": name, **kwargs})
            return cls()
        def apply_chat_template(self, messages, **kwargs):
            calls["processor_calls"].append({"messages": messages, "kwargs": kwargs})
            return Batch()
        def batch_decode(self, ids, **kwargs):
            calls["decode_ids"] = ids
            return ["prefix```html\n" + html + "\n```suffix"]
    class Model:
        device = "audit-no-device"
        @classmethod
        def from_pretrained(cls, name, **kwargs):
            calls["checkpoint_requests"].append({"kind": "model", "name": name, **kwargs})
            return cls()
        def generate(self, **kwargs):
            calls["generate_calls"].append(kwargs)
            return [[7, 8, 9, 10]]
    def renderer(html_path, png_path):
        calls["render_requests"].append({"html": html_path, "png": png_path})
        return False  # explicit unavailable renderer, never fabricate a screenshot
    namespace, record = extract(path, ["QwenModel"],
                                {"os": os, "re": re, "AutoProcessor": Processor,
                                 "Qwen3VLForConditionalGeneration": Model,
                                 "torch": types.SimpleNamespace(bfloat16="audit-dtype-marker"),
                                 "render_aligned_png": renderer})
    model = namespace["QwenModel"]("AUDIT_NO_CHECKPOINT")
    model.save_html = lambda content, path: calls["saved_html"].append({"path": path, "content": content}) or True
    result = model.post("Synthetic audit task", "Click the selected control", "AUDIT_IMAGE_SENTINEL",
                        {"action_type": "click", "index": 0}, "AUDIT_NO_WRITE", 1)
    assert result is None and calls["saved_html"][0]["content"] == html
    assert calls["decode_ids"] == [[9, 10]] and len(calls["render_requests"]) == 1
    return {"sources": [record, source_record(EXTERNAL / "Code2World/android_world/agents/m3a_qwen.py")],
            "executed": "original QwenModel.__init__, post, extract_clean_html through renderer-unavailable branch",
            "evidence": {"calls": calls, "returned": result, "rendered_screenshot": False, "checkpoint_loaded": False},
            "substitutions": ["recording AutoProcessor and Qwen3VL factories replace actual checkpoint loading/inference",
                              "synthetic token arrays and declared HTML fixture replace model output",
                              "save_html captures content in memory; renderer records paths and returns False",
                              "torch dtype is a marker; image input is a sentinel; no tensor/image computation"],
            "scope": "native prompt/token-slicing/HTML-cleanup/render dispatch control flow only; no model or screenshot quality evidence"}


PROJECTS = [
    ("VeriEnv", "VeriEnv-main", audit_verienv, "optional model/browser stack for full synthesis", "JSON task checks map directly; browser actions and website generation require a new environment adapter", ["playwright", "gymnasium"]),
    ("PatchWorld", "PatchWorld", audit_patchworld, "LLM backend for induction; no weights for validator", "JSON observation/action strings + BaseWorldModel predict/correct/readout subclass", []),
    ("WorldCoder", "WorldCoder", audit_worldcoder, "LLM backend for synthesis; none for transition evaluator", "JSON _State/_Action subclasses and Windows-safe execution/timeout backend", ["gymnasium"]),
    ("GIF-MCTS", "code-world-models", audit_gif, "code-generation LLM backend/local weights for full search", "provide JSON transition simulator reward/evaluator and prompt templates; retain search/parser", ["mloggers"]),
    ("PoE-World", "poe-world", audit_poe, "LLM program synthesis and expert fitting; no weights for composition kernel", "encode symbolic issue fields/lists as supported object attributes; replace Atari actions/observations and learner data", ["pygame", "hydra"]),
    ("WMA", "WMA-Agents", audit_wma, "trained world/value/policy models or serving endpoints", "replace WebArena accessibility observations/actions with JSON or browser observation adapter; map predictions to full issue state", ["playwright", "gymnasium"]),
    ("WebDreamer", "WebDreamer", audit_webdreamer, "GPT-4o/Claude service or substitute VLM weights", "render issue UI screenshot and map bulk JSON operation to click/type sequence; parse text changes into JSON for exact scoring", ["anthropic", "playwright"]),
    ("WebEvolver", "SelfEvolvingAgent", audit_webevolver, "trained world model plus policy and self-evolution training setup", "map JSON observations/actions to cognitive-kernel trajectories, generate new SFT data and retrain", ["playwright"]),
    ("WebWorld", "WebWorld", audit_webworld, "generation backend plus judge model for original benchmark", "JSON can be serialized as page text; add dataset task/sample schema; exact JSON evaluation replaces LLM judge", ["jsonlines", "json_repair"]),
    ("Code2World", "Code2World", audit_code2world, "pretrained GD-ML/Code2World 8B weights, Android emulator, VLM/HTML rendering stack", "replace Android screenshots/tap actions with web screenshots/clicks and add HTML-to-business-state readout; JSON exact-state output changes native objective", ["android_env", "playwright"]),
    ("Agent2World", "agent2world", audit_agent2world, "LLM agent backends; optional SFT stage; no weights for parser/ranker", "provide issue simulator/toolkit, test generation and JSON predict API in place of text2world/bytesized tasks", ["anthropic", "gymnasium"]),
]


def main():
    dependencies = {}
    for name in sorted({d for _, _, _, _, _, deps in PROJECTS for d in deps} | {"numpy", "scipy", "torch", "pyflakes", "pydantic", "yaml"}):
        try:
            dependencies[name] = bool(importlib.util.find_spec(name))
        except (ImportError, ValueError):
            dependencies[name] = False
    rows = []
    for name, dirname, runner, weights, adaptation, required in PROJECTS:
        root = EXTERNAL / dirname
        files = list(root.rglob("*.py")) if root.exists() else []
        row = {"project": name, "source_directory": str(root.relative_to(ROOT)).replace("\\", "/"),
               "source_python_files_present": len(files), "weight_or_service_requirement": weights,
               "issue_domain_interface_changes": adaptation,
               "missing_probed_dependencies": [d for d in required if not dependencies[d]],
               "full_original_method_feasibility": "not runnable unchanged on issue_lab: " + adaptation + "; requires " + weights,
               "full_original_method_executed": False}
        readmes = [path for path in (root / "README.md", root / "readme.md", root / "WebEvolver/README.md") if path.exists()]
        row["documentation_provenance"] = [source_record(path) for path in dict.fromkeys(readmes)]
        capture = io.StringIO()
        try:
            if runner is None:
                row.update({"status": "blocked", "executed": "none: expected core Python inference module not yet present in downloaded snapshot",
                            "scope": "source download incomplete at audit time; README describes model/emulator prerequisites",
                            "sources": [source_record(root / "readme.md"), source_record(root / "requirements.txt")],
                            "evidence": {"expected_module": "android_world/agents/m3a_qwen.py",
                                         "exists": (root / "android_world/agents/m3a_qwen.py").exists()}})
            else:
                with contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                    result = runner()
                row.update(result)
                row["status"] = "component_executed"
        except Exception as exc:
            row.update({"status": "blocked", "error": f"{type(exc).__name__}: {exc}",
                        "scope": "no successful execution claimed"})
        if capture.getvalue():
            row["captured_component_output"] = capture.getvalue()[-8000:]
        rows.append(row)
        print(f"{name}: {row['status']}", flush=True)
    output = {"audit_schema": 1, "purpose": "replayable upstream component audit; no paper-method benchmark scores",
              "environment": {"python": sys.version, "platform": platform.platform(), "dependencies": dependencies},
              "restrictions": {"network_calls": 0, "model_service_calls": 0, "learner_files_read": 0,
                               "private_eval_files_read": 0, "external_dependency_installations": 0},
              "fixture": {"source": "handwritten synthetic public-schema example; no domain code or heldout data imported",
                          "transition": dict(zip(("state", "action", "next_state"), fixture()))},
              "projects": rows}
    target = ROOT / "artifacts/upstream_audit.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
