#!/usr/bin/env python3
"""
PDDL Player (minimal CLI)
Usage:
  python player_text2world.py path/to/domain.pddl path/to/problem.pddl
"""

import os
import sys
import re
import time
import argparse
import warnings
import tempfile
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

warnings.filterwarnings("ignore", message=".*Gym has been unmaintained.*")

# Try project-root relative import (robust for running from repo)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.llm import call_llm

# ---- PDDLGym import ----
try:
    from pddlgym.core import PDDLEnv
    PDDL_AVAILABLE = True
except Exception:
    PDDL_AVAILABLE = False


@dataclass
class PDDLStep:
    step_number: int
    state_description: str
    action_taken: Optional[str]
    observation: str
    reward: float
    is_terminal: bool
    llm_reasoning: str
    execution_time: float


@dataclass
class PDDLTrajectory:
    domain_file: str
    problem_file: str
    steps: List[PDDLStep]
    total_reward: float
    success: bool
    total_execution_time: float


class PDDLPlayer:
    def __init__(self, model_name: str = "gpt-4o-mini", max_steps: int = 20, use_llm: bool = True, history_window: int = 3):
        self.model_name = model_name
        self.max_steps = max_steps
        self.use_llm = use_llm
        self.history_window = max(0, int(history_window))
        self.history: List[str] = []

    # ----------------------------
    # GOAL extraction (FIXED)
    # ----------------------------
    def _get_goal_info(self, env: PDDLEnv, problem_file: str) -> str:
        # 1) Try common pddlgym internals
        for attr in ["_problem", "problem"]:
            if hasattr(env, attr):
                prob = getattr(env, attr)
                if hasattr(prob, "goal") and prob.goal is not None:
                    return str(prob.goal)

        # 2) Fallback: parse (:goal ...) from problem.pddl using balanced parentheses
        try:
            txt = Path(problem_file).read_text(encoding="utf-8")
            lower = txt.lower()
            i = lower.find("(:goal")
            if i == -1:
                return "Unknown goal"

            # find first '(' after (:goal
            j = txt.find("(", i)
            if j == -1:
                return "Unknown goal"

            depth = 0
            k = j
            while k < len(txt):
                ch = txt[k]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        return txt[j:k + 1].strip()
                k += 1
        except Exception:
            pass

        return "Unknown goal"

    def play_episode(self, domain_file: str, problem_file: str, verbose: bool = True) -> PDDLTrajectory:
        if not PDDL_AVAILABLE:
            raise RuntimeError("pddlgym is not installed. Install with: pip install pddlgym")

        if not os.path.exists(domain_file):
            raise FileNotFoundError(f"Domain file not found: {domain_file}")
        if not os.path.exists(problem_file):
            raise FileNotFoundError(f"Problem file not found: {problem_file}")

        start_time = time.time()

        # PDDLEnv takes problem_dir (directory). To guarantee it uses exactly the given problem_file,
        # isolate that file in a temp dir with ONLY this file inside.
        isolated_problem_dir = tempfile.mkdtemp(prefix="pddlgym_problem_")
        try:
            isolated_problem_path = Path(isolated_problem_dir) / Path(problem_file).name
            shutil.copy(problem_file, isolated_problem_path)

            env = PDDLEnv(
                domain_file=domain_file,
                problem_dir=str(isolated_problem_dir),
                render=False,
                operators_as_actions=True,
                dynamic_action_space=True,
            )

            obs = env.reset()
            # gymnasium-style reset may return (obs, info)
            if isinstance(obs, tuple) and len(obs) >= 1:
                obs = obs[0]

            traj = PDDLTrajectory(
                domain_file=domain_file,
                problem_file=problem_file,
                steps=[],
                total_reward=0.0,
                success=False,
                total_execution_time=0.0,
            )

            if verbose:
                print("Starting PDDL episode:")
                print(f"  Domain : {Path(domain_file).resolve()}")
                print(f"  Problem: {Path(problem_file).resolve()}")

            step_n = 0
            total_reward = 0.0
            done = False

            while (not done) and step_n < self.max_steps:
                step_start = time.time()

                # available actions
                try:
                    available_actions = list(env.action_space.all_ground_literals(obs))
                except Exception as e:
                    if verbose:
                        print(f"Error getting available actions: {e}")
                    break

                if not available_actions:
                    if verbose:
                        print("No available actions. Episode terminated.")
                    break

                action, reasoning = self._select_action(obs, available_actions, env, problem_file)

                try:
                    step_result = env.step(action)
                    # gym: (obs, reward, done, info) or gymnasium: (obs, reward, terminated, truncated, info)
                    if len(step_result) == 4:
                        next_obs, reward, done, _info = step_result
                    else:
                        next_obs, reward, terminated, truncated, _info = step_result
                        done = bool(terminated or truncated)

                    total_reward += float(reward)

                    step = PDDLStep(
                        step_number=step_n,
                        state_description=self._format_observation(obs),
                        action_taken=str(action),
                        observation=self._format_observation(next_obs),
                        reward=float(reward),
                        is_terminal=bool(done),
                        llm_reasoning=reasoning,
                        execution_time=time.time() - step_start,
                    )
                    traj.steps.append(step)

                    if verbose:
                        print(f"Step {step_n}: {action} -> Reward: {reward}")

                    obs = next_obs
                    step_n += 1

                except Exception as e:
                    if verbose:
                        print(f"Error executing action: {e}")
                    break
                
                try:
                    hist_entry = f"Step {step_n}: {action} | Reward: {reward} | Next: {self._format_observation(next_obs)}"
                    self.history.append(hist_entry)
                    if self.history_window > 0 and len(self.history) > self.history_window:
                        self.history = self.history[-self.history_window:]
                except Exception:
                    pass

            traj.total_reward = total_reward
            traj.success = bool(done) and total_reward > 0
            traj.total_execution_time = time.time() - start_time

            if verbose:
                print(f"Episode completed: {len(traj.steps)} steps, reward: {traj.total_reward:.2f}")

            return traj

        finally:
            # cleanup temp problem dir
            try:
                shutil.rmtree(isolated_problem_dir, ignore_errors=True)
            except Exception:
                pass

    def _select_action(
        self,
        observation: Any,
        available_actions: List[Any],
        env: PDDLEnv,
        problem_file: str
    ) -> Tuple[Any, str]:
        return self._llm_select_action(observation, available_actions, env, problem_file)

    def _llm_select_action(
        self,
        observation: Any,
        available_actions: List[Any],
        env: PDDLEnv,
        problem_file: str
    ) -> Tuple[Any, str]:
        try:
            state_desc = self._format_observation(observation)
            actions_desc = self._format_actions(available_actions)

            # FIXED: get goal robustly
            goal_info = self._get_goal_info(env, problem_file)
            history_desc = "\n".join(self.history[-self.history_window:]) if (self.history_window > 0 and self.history) else "None"

            prompt = f"""You are a PDDL planning agent. Select the best action.

HISTORY (last {self.history_window}):
{history_desc}

CURRENT STATE:
{state_desc}

GOAL:
{goal_info}

AVAILABLE ACTIONS:
{actions_desc}

Respond with:
ACTION: <number>
REASONING: <your reasoning>"""
            # print(f"LLM prompt: {prompt}")
            response = call_llm(
                text=prompt,
                system_prompt="You are a PDDL planning expert.",
                model=self.model_name,
                max_tokens=600,
                temperature=0.1,
            )

            action_match = re.search(r"ACTION:\s*(\d+)", response, re.IGNORECASE)
            reasoning_match = re.search(r"REASONING:\s*(.+)", response, re.IGNORECASE | re.DOTALL)

            if action_match:
                idx = int(action_match.group(1))
                if 0 <= idx < len(available_actions):
                    reasoning = reasoning_match.group(1).strip() if reasoning_match else "LLM selection"
                    return available_actions[idx], reasoning

        except Exception as e:
            # fall back
            return self._heuristic_select_action(available_actions, note=f"LLM failed: {e}")

        return self._heuristic_select_action(available_actions)

    def _heuristic_select_action(self, available_actions: List[Any], note: str = "Heuristic") -> Tuple[Any, str]:
        if not available_actions:
            return None, "No actions available"
        return available_actions[0], f"{note}: selected first action"

    def _format_observation(self, observation: Any) -> str:
        if observation is None:
            return "No observation"
        try:
            if hasattr(observation, "literals"):
                lits = list(observation.literals)
                return "\n".join([f"  - {lit}" for lit in lits]) if lits else "Empty state"
            if isinstance(observation, (list, tuple, set)):
                return "\n".join([f"  - {x}" for x in observation]) if observation else "Empty state"
            return str(observation)
        except Exception:
            return "Error formatting observation"

    def _format_actions(self, actions: List[Any]) -> str:
        return "\n".join([f"{i}: {a}" for i, a in enumerate(actions)])


def main():
    parser = argparse.ArgumentParser(description="PDDL Player (minimal CLI)")
    parser.add_argument("--domain-file", help="Path to domain.pddl")
    parser.add_argument("--problem-file", help="Path to problem.pddl")
    args = parser.parse_args()

    player = PDDLPlayer()  # defaults
    traj = player.play_episode(args.domain_file, args.problem_file, verbose=True)

    print("\nResults:")
    print(f"Success: {traj.success}")
    print(f"Total reward: {traj.total_reward}")
    print(f"Steps: {len(traj.steps)}")
    print(f"Execution time: {traj.total_execution_time:.2f}s")


if __name__ == "__main__":
    main()
