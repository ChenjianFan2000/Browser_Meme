import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.insert(0, project_root)

from .agentic_world_framework import initialize_agent, agent2world_gen_code
from .utils import WorldModelPromptBase

class ByteSized32Prompt(WorldModelPromptBase):
    def __init__(self,task_describe: str):
        super().__init__(task_describe)
        self.task_describe = task_describe
    
    def build_research_prompt(self) -> str:
        return f"""
    <Research Requirements>
    Before generating any code, you must conduct research using the provided tools (browser_search and browser_open) only:
    - First analyze the task/template: enumerate key entities/objects, attributes (with units and ranges), available actions, constraints/invariants, win/loss and scoring, time progression (tick), and interface conventions (e.g., classes/constructors, generatePossibleActions(), step() return order, error handling, and internal state).
    - Gather domain facts that match those elements: typical/allowable ranges and time scales, device/material operating specs and accuracy, safety thresholds/standards, procedural constraints (preconditions/ordering/conservation), terminology and unit conversions; ensure consistency with interface/observation text.
    - You must NOT output any code or pseudocode in this phase; produce a research report only.
    </Research Requirements>
    
    <Task Description>
    {self.task_describe}
    </Task Description>

    <DELIVERABLE>
    Output ONLY a research report—no implementation code. The report must be directly consumable by the Code Agent and the testing agent:
    - implementation_spec (points 1–6 for implementation):
    1) Goal & evaluation (success/failure/scoring)
    2) Objects & class model (core objects; hierarchy/containment)
    3) Key numbers (units/ranges/thresholds/device params/step limit)
    4) Dynamics/transition (heating/cooling/clamps/RNG & seed policy)
    5) Actions & preconditions (action set, guards, error messages)
    6) Interface contract (class/method signatures, step() return order, observation contents, determinism)
    - test_plan (point 7 for testing): happy_path, edge_cases, assertions

    Quality rules:
    - If sources disagree, note the conflict and the rationale for your choice, or mark uncertainty.
    - Do not include implementation details, executable snippets, or pseudocode; describe interfaces with natural language or string signatures only.
    </DELIVERABLE>
    
    <OUTPUT FORMAT>
    <final>
    {{ "research_summary": "...", "implementation_spec": {{ ... }}, "test_plan": {{ ... }} }}
    </final>
    ### END
    </OUTPUT FORMAT>
    """

    def build_gen_code_prompt(
        self,
        research_report: str | None = None,
        feedback: str | dict | None = None,
    ) -> str:
        """
        Build a strict user prompt that forces a single-file return:
        - No tool/file use, no tests, no JSON manifests
        - Exactly one <final> with one ```python code block
        """
        if feedback:
            mode_header = f""" 
            Mode: debug (apply minimal fixes; keep API unchanged)
            <feedback>
            {feedback}
            </feedback>
            """
        else:
            mode_header = f"""            
            {self.task_describe}
            
            <Research Report>
            {research_report}
            </Research Report>
            """

        return f"""
{mode_header}

<ImplementationRequirements>
1) Contract Fidelity:
- You must strictly adhere to the provided template, implementing the required API as described (class/method names, signatures, return order, types). Each function and method must be fully implemented and may not contain placeholders, empty code snippets, or "pass".
2) Determinism and Validation:
- Provide deterministic/seedable behavior where applicable.
- Validate input; raise clear, single-line errors (ValueError/TypeError). 3) Performance and Coding Style:
- Keep code readable and efficient; avoid unnecessary memory allocations in single-step loops.
- Do not use external reinforcement learning frameworks (excluding standard libraries and common Python libraries such as Numpy and Random) unless explicitly permitted by the task/specification.
4) FIX Mode (<Mode>FIX</Mode> mode only):
- Minimize code modifications to fix bugs while preserving the public API and semantics.
5) Action Protocol (Protocol A):
- generatePossibleActions() MUST return Dict[str, List[Any]] whose **keys are fully-formed, executable command strings** that step(actionStr) accepts verbatim. 
- Allowed singletons: "look", "inventory", "help".
- All other actions MUST include explicit targets using these canonical templates:
  • "examine {{name}}"
  • "take {{object}}"
  • "put {{object}} in {{container}}"
- DO NOT return bare verbs like "take"/"open"/"examine" without arguments.
- Keys must be unique and deterministic
- step(actionStr) MUST parse exactly the same strings.
</ImplementationRequirements>

<Output Format>
```python
# Your complete, runnable single-file implementation here.
```
</Output Format>
    """.strip()
    
    def build_play_env_prompt(self, code, code_file_path: str) -> str:
        return f"""
Your task is to interact with the environment code and then analyze the feedback from the interaction and propose modifications

<CodeArtifact path="{code_file_path}">
```python
{code}
```
</CodeArtifact>

<ExecutionPolicy>
- Use the play_env tool only once, with a step limit of 100.
- If the tool fails or throws an error, diagnose based on static review results and the standard output/error output of the single run.
</ExecutionPolicy>

<Procedure>
1) Static review: Walk through the code to identify possible failure points, invariants, and edge cases.
2) Execution (one-time): Call play_env on "{code_file_path}" with a step limit of 100.
3) Diagnose: Correlate output/errors with code locations; identify root causes.
   - Heuristic A: If stderr contains "Too many values to unpack (expected 5)", then step(...) may return more than 5 values (e.g., an extra info dict). For TextGame, step MUST return exactly (observation, score, reward, gameOver, gameWon).
   - Heuristic B (win detection): Treat the run as a WIN only if you can confirm the environment signaled success (e.g., a 5-tuple step where the last element is True, or logs contain "Game Won: True"/"gameWon=True"). Ambiguous or missing win signals count as NOT WON.
4) Suggest: Propose 1–3 minimally achievable fixes, with a brief rationale and (if helpful) precise code snippets.
5) Stop: After the single tool call in step 2, output the answer and do not call any more tools.
</Procedure>

<OutputFormat>
Return exactly one <final> block containing a single JSON object that matches PlayReport:
{{
  "success": true|false,  // True ONLY if the run had no exceptions AND the game was actually WON; if it finished without winning, return false and explain why.
  "analysis": "<2–4 sentences: what happened and why (no long logs)>",
  "suggest_fix": "<1–3 concise, actionable fixes; plain text, bullets allowed>"
}}
No extra text outside <final>. No additional code fences.
</OutputFormat>
""".strip()


    def build_pytest_env_prompt(self, code: str, code_file_path: str) -> str:
        return f"""
You task is to write a pytest file for the following code:

<CodeArtifact path="{code_file_path}">
```python
{code}
```
</CodeArtifact>

<ExecutionPolicy>
- Do not modify the student's source file.
- Create exactly one pytest file at "tests/test_env.py" using file_tool('save').
- Import the module from "{code_file_path}" via importlib (spec_from_file_location + module_from_spec).
- Run tests with code_tool('run', 'pytest -q'); capture exit_code, duration, and stdout/stderr tail.
</ExecutionPolicy>


<TestPlan>
- Sanity: class TextGame can be imported and instantiated with a seed (e.g., TextGame(0)).
- Contract:
  1) getTaskDescription() returns a non-empty string.
  2) generatePossibleActions() returns a dict-like object.
  3) step('look') returns a 5-tuple: (observation, score, reward, gameOver, gameWon).
- Acceptance: success iff pytest exit_code == 0 (all tests pass).
</TestPlan>

<OutputFormat>
Return exactly one <final> block containing a single JSON object that matches PytestReport:
{{
  "success": true|false,
  "analysis": "<2–4 sentence summary/diagnosis>",
  "suggest_fix": "<optional 1–3 bullets with minimal actionable changes>"
}}
</OutputFormat>

""".strip()

    def build_fix_code_prompt(self, code, code_file_path) -> str:
        return super().build_fix_code_prompt(code, code_file_path)

def generate_bytesize_code(
    benchmark_type: str,
    task_describe: str,
    results_base_dir: str = "./result",
    # 添加消融实验控制参数
    enable_research: bool = True,
    enable_player: bool = True,
    enable_pytest: bool = True
) -> str:
    """
    Orchestrate the multi-agent pipeline:
      1. Extract schema
      2. Generate code
      3. Debug and fix iteratively
    Returns the finalized environment code.
    """

    agent2world_agents = initialize_agent(
        benchmark_type,
        results_base_dir,
        enable_research=enable_research,
        enable_player=enable_player,
        enable_pytest=enable_pytest
    )

    bytesied32_prompt = ByteSized32Prompt(task_describe)

    code = agent2world_gen_code(
        agent2world_agents,
        bytesied32_prompt,
        enable_research=enable_research,
        enable_player=enable_player,
        enable_pytest=enable_pytest
    )
    
    return code
