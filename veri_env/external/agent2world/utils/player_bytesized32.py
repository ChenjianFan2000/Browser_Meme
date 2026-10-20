import argparse
import importlib.util
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, List, Optional

# Try project-root relative import (robust for running from repo)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.llm import call_llm

# ------------------------------ utils ------------------------------

def _normalize_actions(actions_any: Any) -> List[str]:
    try:
        if isinstance(actions_any, dict):
            seq = list(actions_any.keys())
        else:
            seq = list(actions_any)
    except TypeError:
        seq = []
    out: List[str] = []
    seen = set()
    for x in seq:
        s = str(x).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


SYSTEM_PROMPT_SEQ = (
    "You are a STRICT action sequencer for a text game.\n\n"
    "Rules:\n"
    "1) Return STRICT JSON array of at most K strings. No prose, no code fences.\n"
    "2) Each string must be EXACTLY one line from ACTIONS.\n"
    "3) Prefer actions that progress the TASK.\n"
    "4) Avoid repeating actions that just failed or were redundant in recent OBS "
    "5) If unsure, prefer information-gathering actions (look/inventory/examine X) first.\n"
)


def _choose_k_with_llm(
    task: str,
    history_block: str,
    actions: List[str],
    k: int,
    *,
    model: str = "gpt-4.1-mini",
) -> List[str]:
    actions_block = "\n".join(actions)
    user_prompt = f"""TASK:
{task}

LAST_TURNS (most recent first):
{history_block}

ACTIONS (choose up to {k}; each must match exactly one line below):
{actions_block}

Return STRICT JSON array of strings (length 1..{k})."""
    resp = call_llm(user_prompt, SYSTEM_PROMPT_SEQ.replace("K", str(k)), model=model)
    if not isinstance(resp, str):
        resp = str(resp)

    # Try parsing JSON array
    try:
        arr = json.loads(resp)
        if not isinstance(arr, list):
            return []
        plan: List[str] = []
        for it in arr[:k]:
            s = str(it).strip()
            if s in actions:
                plan.append(s)
        return plan
    except Exception:
        # Fallback: tolerate \box{...} sequences
        boxes = re.findall(r"\\box\{(.*?)}", resp, flags=re.DOTALL)
        plan: List[str] = []
        for b in boxes:
            s = b.strip()
            if s in actions and len(plan) < k:
                plan.append(s)
        return plan


def _safe_choice(game: Any, actions: List[str]) -> str:
    if not actions:
        return ""
    # Try common RNG attributes for determinism
    for attr in ("rng", "random"):
        rng = getattr(game, attr, None)
        if rng is not None and hasattr(rng, "choice"):
            try:
                return rng.choice(actions)
            except Exception:
                pass
    return random.choice(actions)


def _history_block(act_hist: List[str], obs_hist: List[str], k: int = 4) -> str:
    pairs = []
    n = min(k, len(obs_hist))
    for i in range(1, n + 1):
        a = act_hist[-i] if len(act_hist) >= i else ""
        o = obs_hist[-i]
        pairs.append(f"a: {a}\no: {o}")
    return "\n".join(pairs)


# ------------------------------ env loading ------------------------------

def _load_env_class(
    env_file_path: Optional[str],
    env_class_name: str = "TextGame",
):
    """
    Load the environment class (default: TextGame).
    - If env_file_path is provided, load that .py file via importlib and fetch the class.
    - Otherwise, fallback to `from environment import TextGame`.
    """
    if env_file_path:
        env_file_path = os.path.abspath(env_file_path)
        mod_dir = os.path.dirname(env_file_path)
        if mod_dir and mod_dir not in sys.path:
            sys.path.insert(0, mod_dir)

        spec = importlib.util.spec_from_file_location("loaded_env_module", env_file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load environment module from: {env_file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

        if not hasattr(module, env_class_name):
            raise AttributeError(
                f"Environment file '{env_file_path}' does not define class '{env_class_name}'."
            )
        return getattr(module, env_class_name)

    # Fallback to import by name
    from environment import TextGame  # type: ignore
    if env_class_name != "TextGame":
        raise AttributeError(
            f"env_class_name='{env_class_name}' not found in fallback import 'environment'."
        )
    return TextGame


def _instantiate_env(TextGameCls, seed: int):
    """
    Instantiate the environment with seed.
    Try kwargs style (randomSeed=seed), then positional (seed), then no-arg.
    """
    try:
        return TextGameCls(randomSeed=seed)
    except TypeError:
        try:
            return TextGameCls(seed)
        except TypeError:
            return TextGameCls()


# ------------------------------ main loop ------------------------------

def main_loop(
    *,
    env_file_path: Optional[str] = None,
    env_class_name: str = "TextGame",
    max_steps: int = 100,
    plan_batch: int = 10,
    seed: int = 1234,
    model: str = "gpt-4o-mini",
    verbose: bool = True,
):
    TextGameCls = _load_env_class(env_file_path, env_class_name)
    game = _instantiate_env(TextGameCls, seed)

    # task string if available
    task = ""
    if hasattr(game, "getTaskDescription") and callable(getattr(game, "getTaskDescription")):
        try:
            task = game.getTaskDescription() or ""
        except Exception:
            task = ""

    obs_history: List[str] = []
    act_history: List[str] = []
    initial_obs = getattr(game, "observationStr", "")
    obs_history.append(initial_obs if isinstance(initial_obs, str) else str(initial_obs))

    plan_queue: List[str] = []

    for step_idx in range(max_steps):
        # fetch available actions
        actions = _normalize_actions(game.generatePossibleActions())
        hist_block = _history_block(act_history, obs_history, k=4)

        # Refill plan queue if empty
        if not plan_queue:
            plan_queue = _choose_k_with_llm(task, hist_block, actions, plan_batch, model=model)
            if not plan_queue:
                plan_queue = [_safe_choice(game, actions)]
            elif verbose:
                print(f"[plan] {len(plan_queue)} actions: {plan_queue}")

        # choose next action
        chosen = plan_queue.pop(0) if plan_queue else _safe_choice(game, actions)

        # if chosen became invalid, try immediate replanning
        if chosen not in actions:
            replanned = _choose_k_with_llm(task, hist_block, actions, max(1, plan_batch - 1), model=model)
            if replanned:
                chosen = replanned.pop(0)
                plan_queue = replanned + plan_queue
            else:
                chosen = _safe_choice(game, actions)

        # step env
        obs, score, reward, over, won = game.step(chosen)

        if verbose:
            print(f"[{step_idx:03d}] action: {chosen}")
            print(f"obs: {obs if isinstance(obs, str) else str(obs)}")
            print(f"score: {score} (reward: {reward})  over={over} won={won}")
            print("-" * 60)

        act_history.append(chosen)
        obs_history.append(obs if isinstance(obs, str) else str(obs))

        if over:
            break


# ------------------------------ CLI ------------------------------

def _parse_args():
    p = argparse.ArgumentParser(description="LLM-driven action sequencer for TextGame environments.")
    p.add_argument("--env-file", type=str, default=None, help="Path to environment .py file (contains TextGame class).")
    p.add_argument("--env-class", type=str, default="TextGame", help="Class name inside the env module (default: TextGame).")
    p.add_argument("--max-steps", type=int, default=100, help="Maximum number of environment steps.")
    p.add_argument("--plan-batch", type=int, default=10, help="How many actions to request per LLM planning round.")
    p.add_argument("--seed", type=int, default=1234, help="Seed to initialize the environment RNG.")
    p.add_argument("--model", type=str, default="gpt-4o-mini", help="LLM model name passed to call_llm.")
    p.add_argument("--quiet", action="store_true", help="Suppress verbose prints.")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main_loop(
        env_file_path=args.env_file,
        env_class_name=args.env_class,
        max_steps=args.max_steps,
        plan_batch=args.plan_batch,
        seed=args.seed,
        model=args.model,
        verbose=not args.quiet,
    )