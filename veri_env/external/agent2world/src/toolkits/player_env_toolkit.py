from __future__ import annotations

import shlex
from typing import Any, Dict, List, Optional

from src.toolkits import FunctionTool
from src.toolkits.sandbox_toolkit import SandboxToolkit
from src.toolkits.base import BaseToolkit
from src.models import BaseModelBackend
from src.messages import OpenAIMessage

# Mapping from benchmark type to the player script on the host side.
BENCHMARK_FILE_PATH = {
    "cwmb":       "utils/player_cwmb.py",
    "bytesized32": "utils/player_bytesized32.py",
    "text2world":       "utils/player_text2world.py",
}

BENCHMARK_CLASS_NAME = {
    "cwmb":       "",
    "bytesized32": "TextGame",
    "text2world":       "",
}


class PlayerEnvToolkit(BaseToolkit):
    r"""Run a benchmark-specific "player" script inside a persistent sandbox and analyze its output.

    Exposed tool: `play_env`

    Workflow:
      1) On initialization, the toolkit uploads the appropriate player script into the sandbox as `eval_env.py`,
         and uploads `utils/llm.py`.
      2) `play_env(...)` executes `eval_env.py` in the sandbox with the provided environment file and step limit.
      3) The sandbox returns normalized execution results.

    Args:
        benchmark_type (str): One of {"cwmb", "bytesize32", "text2world"}.
        sandbox_toolkit (SandboxToolkit): A prepared SandboxToolkit instance used to execute code and manage files.
        timeout (Optional[float]): Optional timeout used by BaseToolkit (if applicable in your stack).
        env_requirements (Optional[List[str]]): Pip packages to install in the sandbox before execution.
        default_workdir (Optional[str]): If set, the command will first `cd` into this directory inside the sandbox.
    """

    def __init__(
        self,
        benchmark_type: str,
        sandbox_toolkit: SandboxToolkit,
        simulator = None,
        timeout: Optional[float] = None,
        env_requirements: Optional[List[str]] = None,
        default_workdir: Optional[str] = None,
    ) -> None:
        super().__init__(timeout=timeout)

        if benchmark_type not in BENCHMARK_FILE_PATH:
            raise ValueError(
                f"Unknown benchmark_type: {benchmark_type!r}. "
                f"Valid options: {list(BENCHMARK_FILE_PATH.keys())}"
            )

        self.sandbox_toolkit = sandbox_toolkit
        self.benchmark_type = benchmark_type
        self.simulator = simulator
        self.env_requirements = list(env_requirements or [])
        self.default_workdir = default_workdir

        # Upload the selected player into the sandbox as eval_env.py and ensure `utils/llm.py` is present.
        file_map = {
            BENCHMARK_FILE_PATH[self.benchmark_type]: "eval_env.py",  # exact file mapping
            "utils/llm.py": "utils/llm.py",                          # exact file mapping
        }
        res = self.sandbox_toolkit.import_file_map(file_map)
        if not res.get("success", False):
            raise RuntimeError(f"Failed to import player files into sandbox: {res.get('error')}")
        
    
    def _make_openai_message(self,player_result:Dict[str,Any]) -> List[OpenAIMessage]:
        
        system_prompt = """
            You are an expert evaluator of text-based game ENVIRONMENTS.
            Your analysis must focus on the environment implementation and its contract with the runner,
            not on the agent's strategy. Be concise and actionable.

            Priorities (environment-centric):
            - API contract: generatePossibleActions() returns a flat List[str]; step(action) returns (observation:str, score:float, reward:float, done:bool, won:bool).
            - Determinism & seeding: stable transitions under a fixed seed; no hidden randomness that breaks reproducibility.
            - Action space integrity: valid/unique strings; no impossible actions; container logic consistent; verbs mapped correctly.
            - Termination & scoring: done/won conditions reachable; score/reward monotonicity and correctness.
            - Exceptions & type errors: tracebacks, attribute errors, wrong return types, None where strings are expected, etc.
            - State mutation: objects/containers update consistently; no stale references or race-like conditions.
            - Observations: clear/consistent strings; no excessive verbosity; no leaking internal debug artifacts.

            If the run is successful and the task is completed, return a brief PASS summary and optional minor improvements only.
            If the run fails or seems degenerate, return a short root-cause analysis and concrete fixes in priority order.
        """
        user_prompt = f"""
            === RUN SUMMARY ===
            {player_result}
            Please analyze the run, identify root causes for any failures or degenerate behavior,
            and propose concrete fixes. If the agent appears stuck repeating observation actions,
            explain how to adjust ranking, planning batch size, history conditioning, or fallback logic.
        """
        openai_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        return openai_messages
    
    def _play_bytesized32(self, code_file_path: str, step_limit: int = 60) -> Dict[str, Any]:
        
        bench_class = BENCHMARK_CLASS_NAME.get(self.benchmark_type) or None

        cmd_parts: List[str] = [
            "python",
            "eval_env.py",
            "--env-file", code_file_path,
            "--max-steps", str(step_limit),
        ]
        if bench_class:
            cmd_parts += ["--env-class", bench_class]

        # Quote each part to be safe with spaces/special characters.
        cmd_str = " ".join(shlex.quote(p) for p in cmd_parts)

        # If a default working directory is provided, change into it first.
        if self.default_workdir:
            cmd_str = f"cd {shlex.quote(self.default_workdir)} && {cmd_str}"

        # Execute inside the sandbox. Any per-call dependencies are installed beforehand.
        play_result = self.sandbox_toolkit.run_bash(
            bash_cmd=cmd_str,
            env_requirements=self.env_requirements,
        )
        return play_result

    def _play_cwmb(self, file_path: str) -> Dict[str, Any]:
        code_program = self.sandbox_toolkit.only_read_file(file_path=file_path)
        prediction_success_rate,extra_info = self.simulator.check_agentic_code(code_program)
        return {
            "success_rate": prediction_success_rate,
            "extra_info": extra_info
        }
    
    def _play_pddl(self, file_path: str, problem_pddl_path: str) -> Dict[str, Any]:
        """
        Test PDDL domain using utils/player_text2world.py via subprocess execution
        """
        
        cmd_parts: List[str] = [
            "python",
            "utils/player_text2world.py",
            "--domain-file", file_path,
            "--problem-file", problem_pddl_path or "",
        ]

        # Quote each part to be safe with spaces/special characters.
        cmd_str = " ".join(shlex.quote(p) for p in cmd_parts)
                
        # If a default working directory is provided, change into it first.
        if self.default_workdir:
            cmd_str = f"cd {shlex.quote(self.default_workdir)} && {cmd_str}"

        # Execute inside the sandbox. Any per-call dependencies are installed beforehand.
        play_result = self.sandbox_toolkit.run_bash(
            bash_cmd=cmd_str,
            env_requirements=self.env_requirements,
        )
        return play_result
    
    def play_env(self, file_path: str, problem_pddl_path: str = None, step_limit: int = 60) -> Dict[str, Any]:
        r"""Execute the uploaded `eval_env.py` inside the sandbox against the provided environment file.

        The command constructed is equivalent to:
            `python eval_env.py --env-file <file_path> [--env-class <ClassName>] --max-steps <step_limit>`

        Notes:
            - `file_path` must be the path to the environment file **inside the sandbox**.
            - If a benchmark requires a specific environment class name, it is passed via `--env-class`.
            - If `default_workdir` was set during initialization, the command will `cd` into it first.

        Args:
            file_path (str): Path to the environment Python file inside the sandbox (e.g., `src/environment.py`).
            problem_pddl_path (str): Path to the PDDL problem file inside the sandbox (e.g., `src/problem.pddl`).
            step_limit (int): Maximum number of steps to run the environment.

        Returns:
            Dict[str, Any]: A dictionary including an execution success flag, standard output, standard error,
            the process return code, and an error message if one occurred.
        """
        if self.benchmark_type == "bytesized32":
            play_result = self._play_bytesized32(file_path,step_limit)
        elif self.benchmark_type == "cwmb":
            play_result = self._play_cwmb(file_path)
        elif self.benchmark_type == "text2world":
            play_result = self._play_pddl(file_path,problem_pddl_path)
        else:
            raise ValueError(f"Unsupported benchmark type: {self.benchmark_type}")
        
        return play_result


    # ----------------------------- tool exposure control -----------------------------

    def get_tools(self) -> List[FunctionTool]:
        """Expose only `play_env` as a tool."""
        return [FunctionTool(self.play_env)]
