# -*- coding: utf-8 -*-
"""
env_eval.py
-----------
Expose ONLY `play_env` as an agent tool.
Internal helpers (`_init_agent`, `_build_user_prompt`) are NOT tools.

This toolkit builds a self-contained user prompt that instructs an agent to:
1) save a text-game environment into a sandbox,
2) write a minimal policy runner that queries an LLM for the next action,
3) iterate a concise ReAct loop,
4) print exactly one JSON line as the final result.

Project-internal dependencies:
    - src.agents: ChatAgent, PlayerAgent, DeepResearchAgent
    - src.types: ModelPlatformType, ModelType
    - src.models: ModelFactory
    - src.prompts: PlayerPromptTemplateDict, DeepResearchPromptTemplateDict
    - src.toolkits: WebSearchToolkit, SandboxToolkit, FunctionTool
    - src.toolkits.base: BaseToolkit
"""

from __future__ import annotations

from typing import Optional, List, Dict

from src.agents import ChatAgent, PlayerAgent, DeepResearchAgent
from src.types import ModelPlatformType, ModelType
from src.models import ModelFactory
from src.prompts import PlayerPromptTemplateDict, DeepResearchPromptTemplateDict
from src.toolkits import WebSearchToolkit, SandboxToolkit, FunctionTool
from src.toolkits.base import BaseToolkit


class EnvEvalToolkit(BaseToolkit):
    r"""Toolkit to *play* (i.e., interact with) a text-game environment via a ReAct-style runner.

    Public tool:
        - play_env(code_file_path, ...): Build the prompt, run the agent once, and return its raw result.

    Private helpers (NOT exported as tools):
        - _init_agent(): construct the underlying ChatAgent (DeepResearchAgent by default)
        - _build_user_prompt(): build the self-contained instruction with embedded EnvCode

    Args:
        use_deep_research (bool): If True, use DeepResearchAgent; otherwise use PlayerAgent.
        model_platform (ModelPlatformType): LLM platform for ModelFactory (e.g., OPENAI).
        model_type (ModelType): LLM model type (e.g., GPT_4O_MINI).
        model_temperature (float): Default temperature for the single model instance.
        default_file_map (Optional[Dict[str, str]]): File mapping passed to SandboxToolkit.
        default_requirements (Optional[List[str]]): Requirements passed to SandboxToolkit.
        timeout (Optional[float]): Timeout (seconds) used by BaseToolkit's with_timeout wrapper.
    """

    def __init__(
        self,
        use_deep_research: bool = True,
        model_platform: ModelPlatformType = ModelPlatformType.OPENAI,
        model_type: ModelType = ModelType.GPT_4O_MINI,
        model_temperature: float = 0.0,
        default_file_map: Optional[Dict[str, str]] = None,
        default_requirements: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.use_deep_research = use_deep_research
        self.model_platform = model_platform
        self.model_type = model_type
        self.model_temperature = model_temperature
        self.default_file_map = default_file_map or {
            # Save LLM helper into sandbox under "utils/llm.py"
            "src/utils/llm.py": "utils",
            # Default mapping if your env code imports "src.environment"
            "environment.py": "src",
        }
        self.default_requirements = default_requirements or ["pytest"]

    # ------------------------------- internal helpers (NOT tools) -------------------------------

    def _init_agent(self) -> ChatAgent:
        """Create a single-model agent with WebSearchToolkit + SandboxToolkit tools attached."""
        single_model = ModelFactory.create(
            model_platform=self.model_platform,
            model_type=self.model_type,
            model_config_dict={"temperature": self.model_temperature},
        )

        # Aggregate tools used by the agent (web + sandbox)
        web_search_toolkit = WebSearchToolkit()
        tools = web_search_toolkit.get_tools()

        sandbox_toolkit = SandboxToolkit(
            default_file_map=self.default_file_map,
            default_requirements=self.default_requirements,
        )
        tools += sandbox_toolkit.get_tools()

        # Choose agent flavor
        if self.use_deep_research:
            agent = DeepResearchAgent(
                system_message=DeepResearchPromptTemplateDict.build(),
                model=single_model,
                tools=tools,
                auto_save=True,
            )
        else:
            agent = PlayerAgent(
                system_message=PlayerPromptTemplateDict.build(),
                model=single_model,
                tools=tools,
                auto_save=True,
            )
        return agent

    def _build_user_prompt(
        self,
        code_file_path: str,
        step_limit: int = 60,
        max_attempts: int = 3,
        env_module_name: str = "env_under_test",
        runner_filename: str = "policy_runner.py",
        llm_model_hint: str = "gpt-4o-mini",
    ) -> str:
        """Build the self-contained instruction, embedding the env source under <EnvCode>."""
        with open(code_file_path, "r", encoding="utf-8") as f:
            env_code = f.read()

        # NOTE: Double curly braces to escape Python f-string formatting in the JSON example below.
        return f"""
<Goal>
Play a text-game environment by writing a minimal policy runner, executing it in the sandbox, and reporting results.
Use a concise ReAct loop (Think -> Tool -> Observe -> Reflect).
</Goal>

<Tools>
You may use ONLY these sandbox tools:
- file_tool("save", file_path, content): write files.
- file_tool("read", file_path): read files (optional).
- code_tool("run_bash", bash_cmd): run shell commands (e.g., "python {runner_filename}").
- code_tool("run_code", code): quick snippets (optional).

Inside the runner you can import an LLM helper:
- from utils.llm import call_llm
  def call_llm(text, system_prompt="...", model="{llm_model_hint}", max_tokens=120, temperature=0.3) -> str
Use it as an action selector given (observation, valid action list). Do NOT print its raw responses.
</Tools>

<EnvCode module="{env_module_name}">
```python
{env_code}
````

</EnvCode>

<Code-Interact>
1) Save the environment as "{env_module_name}.py" via file_tool("save", ...).
2) Create "{runner_filename}" that:
   - imports TextGame from "{env_module_name}".
   - imports: json, traceback; and from utils.llm import call_llm.
   - main logic:
     a) env = TextGame(randomSeed=0)
     b) history = []
     c) for t in range({step_limit}):
        - obs = env.observationStr
        - actions = list(env.generatePossibleActions().keys())
        - Compose a SHORT prompt for call_llm, e.g.:
          "You are choosing ONE next action from this list.\\n"
          "Output EXACTLY one valid action string. No extra text.\\n"
          "OBS:\\n{{obs_tail}}\\nACTIONS:\\n{{actions}}"
          Use a minimal system prompt that enforces: "return only one valid action string".
        - action = call_llm(text, model="{llm_model_hint}", max_tokens=64, temperature=0)
          If invalid/empty, fallback to a simple heuristic (e.g., first valid action).
        - obs, score, reward, over, won = env.step(action)
        - history.append(action)
        - if over: break
     d) Always print exactly ONE JSON line to stdout:
        {{
          "done": bool(over), "game_won": bool(won), "score": float(score),
          "step": int(len(history)), "history": history[-10:],
          "obs_tail": str(obs[-200:]) if isinstance(obs, str) else "",
          "error": None
        }}
     e) Exception handling:
        catch exceptions -> print the SAME JSON schema with "error" set to the traceback string; keep other fields best-effort.
   - Important:
     - The runner should not print anything except the FINAL JSON line to stdout.
     - Do NOT modify environment logic; only write/iterate the runner.
     - Use only valid action strings returned by generatePossibleActions().
</Code-Interact>

<ReAct-Loop max_attempts="{max_attempts}">
THINK: If not won, decide what to adjust (prompt strategy, fallbacks, simple heuristics).
TOOL: Update "{runner_filename}" via file_tool("save", ...); run with code_tool("run_bash", "python {runner_filename}").
OBSERVE: Parse the runner's stdout; extract the single JSON line and stderr (if any).
REFLECT: If "game_won" is true -> stop. Else revise and retry (<= {max_attempts} attempts total).
</ReAct-Loop>

<Constraints>
- Deterministic when possible (temperature=0 for call_llm).
- Keep LLM prompts short and focused; pass only the tail of the observation and a compact action list.
- No interactive input() in runner.
- Final stdout must be exactly one JSON line.
</Constraints>

<Output>
Return ONLY:
1) A brief status summary (<= 5 lines).
2) A fenced code block with the final "{runner_filename}".
3) A fenced JSON block with the final parsed result (the JSON printed by the runner).
</Output>
"""

    def play_env(
        self,
        code_file_path: str,
        step_limit: int = 60,
        max_attempts: int = 3,
        env_module_name: str = "env_under_test",
        runner_filename: str = "policy_runner.py",
        llm_model_hint: str = "gpt-4o-mini",
    ) -> str:
        """Public tool entrypoint: build prompt, run one agent step, and return the raw result string.

        Args:
            code_file_path (str): Path to the environment source code to embed into <EnvCode>.
            step_limit (int): Max steps in the runner loop.
            max_attempts (int): Max ReAct iterations for improving the runner.
            env_module_name (str): Module name used when saving env into the sandbox.
            runner_filename (str): The file name of the runner in the sandbox.
            llm_model_hint (str): Model hint passed to `call_llm` inside the runner.

        Returns:
            str: Whatever `agent.step()` returns (stringified). Caller can parse as needed.
        """
        try:
            agent = self._init_agent()
            user_prompt = self._build_user_prompt(
                code_file_path=code_file_path,
                step_limit=step_limit,
                max_attempts=max_attempts,
                env_module_name=env_module_name,
                runner_filename=runner_filename,
                llm_model_hint=llm_model_hint,
            )
            result = agent.step(user_prompt)
            return str(result)
        except Exception as e:
            # Defensive: never raise inside a tool; return a readable message
            return f"[EnvEvalToolkit] Failed to play env: {e}"

    # ------------------------------ non-tool convenience aliases ------------------------------

    def interact_env(self, *args, **kwargs) -> str:
        """Back-compat alias emphasizing 'interaction' (NOT exported as a tool)."""
        return self.play_env(*args, **kwargs)

    def simulate_env(self, *args, **kwargs) -> str:
        """Back-compat alias for previous name (NOT exported as a tool)."""
        return self.play_env(*args, **kwargs)

    def evaluate_text_game(self, *args, **kwargs) -> str:
        """Back-compat alias (NOT exported as a tool)."""
        return self.play_env(*args, **kwargs)

    # --------------------------------- tool exposure control ---------------------------------

    def get_tools(self) -> List[FunctionTool]:
        """Expose ONLY `play_env` as an agent tool."""
        return [FunctionTool(self.play_env)]
