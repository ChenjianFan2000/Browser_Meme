from .agentic_world_framework import initialize_agent, agent2world_gen_cwmb_code
from .utils import WorldModelPromptBase
from typing import Any
import re

class MctsPrompt(WorldModelPromptBase):
    def __init__(self, environemnt:str,task_describe: str,simulator:Any):
        self.environemnt = environemnt
        self.task_describe = task_describe
        self.research_report = ""
        with open(simulator.i_prompt_path, "r") as f:
            prompt = f.read()
        self.i_base_prompt = prompt
        
        with open(simulator.g_prompt_path, "r") as f:
            prompt = f.read()
        self.g_base_prompt = prompt
        
        with open(simulator.f_prompt_path, "r") as f:
            prompt = f.read()
        self.f_base_prompt = prompt
        self.gen_code_common = """
        
        <Output Format>

        <final>
        <code_file_path>
        The entrypoint file path of the generated code.
        </code_file_path>
        <entrypoint_code>
        ```python
        # Your complete, runnable single-file implementation here.
        ```
        </entrypoint_code>
        </final>

        </Output Format>
        
        """
    def build_research_prompt(self) -> str:
        return f"""
You are a world-class Systems Analyst and Technical Specification Writer, specializing in creating reinforcement learning environments. Your mission is to transform an ambiguous task description into a precise, actionable, and verifiable technical specification.

<Environment Name>
{self.environemnt}
</Environment Name>

<TASK DESCRIPTION>
{self.task_describe}
</TASK DESCRIPTION>

<Workflow>
Please strictly follow the following six-step process:
1. **Deconstruction and Analysis (Use Version Locking)**
- Identify all ambiguities, gaps, and conflicts in the task description.
- Lock the exact environment version and key library versions (record name, version, and source link).
- Categorize gaps by type: missing value/unit/range boundary/time-sensitive/ambiguous reference/unclosed list/conflict/no provenance.
2. **Planning and Investigation (Authoritative Search + Evidence Log)**
- For each high/mid-level project, write 1-2 focused queries that include: synonyms/abbreviations, site filters, authoritative domains (e.g., site:numpy.org, site:docs.python.org),
and recency windows (e.g., after 2024-01-01 or "last 2 years").
- Execute the query using browser_search and open ≥ 2 trusted results with browser_open.
- If the top source disagrees, open ≥1 additional authoritative sources and triangulate.
- Create an evidence log entry for each opened page: Title | Organization/Author | Version/Submission | URL (+ archived URL)
| Publication Date | Access Date (Asia/Singapore) | 3 Key Facts | Confidence (High/Medium/Low).
3. **Synthesis and Citation (Conflict Resolution)**
- Integrate the findings into a concise evidence summary with citations.
- When sources conflict, explain the differences and justify the chosen resolution (related to version locking).
4. **Refinement and Improvement (Specification Patch)**
- Generate a structured "diff": action/observation space; rewards; termination/truncation; timing (dt/frame_skip); seeding and certainty; numerical tolerances; dependencies; interface flags.
5. **Formalization and Finalization (Ready-to-Use Specification)**
- Write the final specification according to the <Output Format> (OUTPUT_FORMAT>), including the public API, core logic, usage scenarios, and a verification plan aligned with metrics and statistical validation.
6. **Review and Self-Correction (Compliance Check)**
- Verify conformance to the <Output Constraints> (OUTPUT_CONSTRAINTS>), version consistency, SI units, ISO dates, and the inclusion of any code.
</Workflow>

<OUTPUT_CONSTRAINTS>
* Strictly adhere to the structure defined in <PLANNING_STRUCTURE>.
* Do NOT output runnable code definitions (classes, functions). Only may include short illustrative snippets or pseudo-code.
* All claims about industry standards or common practices MUST be supported by citations.
* Use ISO-8601 dates (e.g., 2025-09-02).
* Use SI units for physical and mathematical quantities.
* Data-leakage rule: Do not access, copy, quote, or derive from raw source code repositories. Prefer official documentation, standards, papers, or reputable secondary sources. If the only available evidence is a code repository, summarize behavior without copying code and mark it as an inference with risks.
</OUTPUT_CONSTRAINTS>

<PLANNING_STRUCTURE>
Your output must begin with this planning and analysis section.
1. **Ambiguity Analysis**
   - List each ambiguity/vagueness/conflict and mark Impact: High / Medium / Low.
   - Cover at least: missing numeric value, missing unit, missing boundary/range, time-sensitive items,
     unclear references, open lists ("etc."/"e.g."), conflicts, and missing citation.
2. **Investigation Plan**
   - For each High/Medium item, provide one atomic question.
   - For each question, provide 1–2 executable queries including: synonyms/abbreviations, a site filter to authoritative
     domains, and a time window (e.g., after:2024-01-01 or "past 2 years").
   - State the minimum evidence policy: High/Medium → ≥2 credible sources; if disagreement → add ≥1 more for triangulation.
</PLANNING_STRUCTURE>

<Formula requirements>
* For any formula, define all symbols, units, and applicability constraints.
* Cite the source of the formula immediately after its definition.
* Provide the complete formula rather than a descriptive explanation.
</Formula requirements>

<OUTPUT_FORMAT>
Please provide the final specification document structured as follows. This is the primary deliverable. Do NOT include code.

<Version & Provenance>
* Environment name and version lock (e.g., vX.Y); document/library versions; commit hash (if applicable).
* Source release date AND Accessed date (ISO-8601, Asia/Singapore).
* Scope note: this specification normalizes any legacy or paper-specific differences.

<Evidence Summary>
* For each ambiguity/issue, summarize findings with references.
* Citation format: [Source Name, YYYY-MM-DD] "Optional ≤20-word quote."
* If sources conflict, describe the conflict and justify the chosen resolution.

<Spec Patch>
* Structured key–value decisions that resolve ambiguities (the "diff").
* Cover: action/observation spaces; reward function; termination/truncation; timing (dt/frame_skip); seeding; dependencies; numeric tolerances; interface flags.
* Example entries: `reward.penalty.late = -0.5`, `termination.max_steps = 1000`, `obs.dtype = float32`.
</Spec Patch>

<Theoretical Foundations>
* Formal MDP definition and core equations (e.g., discounted return, Bellman optimality).
* Domain formulas (physics/math) with full definitions, units, ranges, and assumptions.
* If shaping is used, specify potential-based shaping formula and cite invariance guarantees.
* Provide a Symbol Table listing every symbol (name, unit, allowable range).

<Final Specification>
* Standalone, unambiguous description integrating the Spec Patch.
* Public API Definition: class name; __init__ parameters; method signatures (reset, step, set_state, etc.) with type hints (no code).
* Core Logic Description: precise `reset`/`step` semantics; state update rules; reward calculation; termination and truncation checks; info fields.
* Usage Scenarios & Examples: at least two multi-step traces. For each step, list:
  - observation, action, reward, terminated (bool), truncated (bool), info (dict)
  - Use SI units and exact values/ranges; no vague terms ("about", "etc.").

<Assumptions & Risks>
* Assumptions made due to missing/conflicting evidence; risks and potential impacts.

<Library Usage>
* How official documentation informs interfaces, units, and signatures.
* Allowed libraries: Python standard library and NumPy only.
* Cite specific APIs (e.g., numpy.random.Generator seeding; np.clip semantics; math module functions).
* State explicitly: only standard library and NumPy are used; no external dependencies are introduced by this spec and no source code is copied; documentation is used only to clarify behavior.

</OUTPUT_FORMAT>

<CORE_PRIORITIES>
Correctness (evidence-backed) > Reproducibility (versioning & seeding) > Clarity (unambiguous) > Completeness (no open-ended lists).
</CORE_PRIORITIES>
""".strip()

    def build_gen_code_prompt(
        self,
        feedback: str | dict | None = None,
        debug: bool = False
    ) -> str:
        if debug:
            return self.build_fix_code_prompt(feedback)
        elif feedback:
            return self.build_improve_code_prompt(feedback)
        else:
            return self.build_generate_code_prompt()
    def build_generate_code_prompt(self) -> str:
        return f"""
{self.task_describe}


<Research Report>
{self.research_report}
</Research Report>

<Workflow>
1. **Deconstruct Specification:** Carefully review the `<Task Describe>,<Research Report>` to fully understand the environment's specification, including state/action spaces, dynamics, reward function, and termination conditions.
2. **Mathematical Modeling:** Evaluate if the task requires mathematical simulation. If so, implement the mathematical models using standard numerical methods.
3. **Model Design:** Design the mathematical model structure and implement it directly in the Python file using standard library and NumPy.
4. **Plan Class Structure:** Outline the `Environment` class, including its internal state variables, helper methods, and the public interface (`__init__`, `reset`, `set_state`, `step`).
5. **Implement Complete Code:** Write the full implementation of the `Environment` class.
6. **Self-Correction Review:** Meticulously check that the generated code fully complies with the `<TASK DESCRIPTION>`, the `<Research Report>`, and all `<ImplementationRequirements>`.
7. **Finalize Output:** Present the complete, reviewed, and runnable single-file code in the specified final format.
</Workflow>

<ImplementationRequirements>
1) Interface (single file):
Implement a complete, self-contained Python class `Environment` with:
  • `__init__(self, seed: int | None = None)`  
  • `reset(self, seed: int | None = None) -> ndarray`  — reinitialize the episode and **return the initial observation** in canonical shape  
  • `set_state(self, state)`  — must accept ndarray OR list/tuple in canonical shape  
  • `step(self, action) -> tuple[ndarray, float, bool]`  — (observation, reward, done)
Requirements:
- **Single-file constraint**: All code, including model definitions, must be in one Python file
- For mathematical simulations, implement numerical methods directly within the class
- Explicitly define state, action, and observation spaces (types, shapes, ranges, formats)
- Provide reproducibility (seeding) via constructor and/or a `seed(int)` method
- Be robust to common representations:
  - `set_state`: list/tuple/ndarray of the same logical content
  - `step`: int / numpy integer scalar / 0-D or 1-D len-1 ndarray, etc. (convert to canonical form; raise clear TypeError/ValueError on invalid)
- No dependence on external RL frameworks; no Gym inheritance
- No external file dependencies (model definitions must be embedded)
- Maintain internal state consistency; allow reconstruction from observations where applicable
- Clean, readable code suitable for RL experimentation

2) Determinism & validation:
   - Provide reproducibility via seed (constructor and/or `seed(int)` method)
   - Normalize inputs: accept equivalent representations (e.g., numpy scalar/int/len-1 array) and convert to canonical
   - Validate inputs; raise clear one-line errors (ValueError/TypeError) on invalid shapes/ranges

3) Dynamics (MCTS/control oriented):
   - For mathematical simulations, implement appropriate numerical integration methods (e.g., Euler, Runge-Kutta) using standard library and NumPy
   - Choose and document an integration scheme (e.g., implicit integrator, Explicit Euler) consistent with the research report
   - Use a stable `dt`; clamp to safety bounds; keep all values finite (no NaN/Inf)
   - Keep per-step computation efficient and allocation-light

4) Dependencies & style:
   - No Gym inheritance or external RL frameworks
   - **Allowed libraries: Python standard library and NumPy only**
   - For mathematical/physics tasks, implement numerical methods directly using NumPy and standard library functions
   - Clean, readable code suitable for RL experimentation
   - All dependencies must be standard library or NumPy

</ImplementationRequirements>

{self.gen_code_common}

    """.strip()
    
    def build_fix_code_prompt(self, feedback) -> str:
        return f"""
      {self.task_describe}
      {self.f_base_prompt}

      <Workflow>
      1. **Error Analysis:** Carefully analyze the feedback to identify specific errors, exceptions, or failures in the existing code.
      2. **Root Cause Investigation:** Trace back to the underlying causes - whether it's logic errors, type mismatches, model syntax issues, missing edge cases, incorrect numerical method usage, or incorrect implementations.
      3. **Targeted Fix Planning:** Plan minimal, focused changes that directly address the identified issues without breaking existing functionality.
      4. **Code Correction:** Implement the specific fixes, ensuring they resolve the reported problems while maintaining code integrity and single-file constraint. For numerical issues, consider standard library and NumPy best practices.
      5. **Validation Review:** Verify that the fixes address all reported issues and don't introduce new problems.
      </Workflow>
      
      <feedback>
      {feedback}
      </feedback>
      {self.gen_code_common}
      
      """
    
    def build_improve_code_prompt(self, feedback) -> str:
        return f"""
      {self.task_describe}
      {self.i_base_prompt}
    
      <Workflow>
      1. **Performance Gap Analysis:** Analyze the feedback to identify areas where the current implementation falls short of requirements or optimal performance.
      2. **Enhancement Opportunity Assessment:** Review the existing code structure, model design, and the research report to identify specific improvement opportunities, particularly for numerical method implementation.
      3. **Optimization Strategy Planning:** Plan targeted enhancements that improve functionality, performance, or compliance while preserving working components and maintaining single-file constraint. Consider standard library and NumPy optimizations.
      4. **Incremental Code Enhancement:** Implement improvements systematically, building upon the existing codebase rather than rewriting from scratch.
      5. **Quality Assurance Review:** Ensure enhancements meet the requirements and maintain backward compatibility where applicable.
      </Workflow>
      
      <research_report>
      {self.research_report}
      </research_report>
      <feedback>
      {feedback}
      </feedback>
      {self.gen_code_common}
      """


    def build_play_env_prompt(self, code: str, code_file_path: str) -> str:
        return f"""
    Your task is to inspect the environment code, run it once, interpret the signals, and propose minimal fixes.

    <CodeArtifact path="{code_file_path}">
    ```python
    {code}
    ```

    </CodeArtifact>

    <ExecutionPolicy>
    - Call the play_env tool exactly once on "{code_file_path}".
    - If the tool fails or cannot run, rely on static review and any logs, but still produce the required output.
    </ExecutionPolicy>

    <Rubric>
    Success:
    - If per-step signals exist: success = true iff the run ends without exceptions AND there is no misclassified_transition with (valid == false OR state_matches/obs_matches == false).
    - For numeric deltas, treat matches = true if max_abs_error ≤ 1e-3 OR rel_error ≤ 1e-3.
    - If only aggregate metrics exist: if success_rate is present, success = true iff no exceptions AND success_rate ≥ 0.95; otherwise, success = true iff no exceptions AND no clear invariant/contract violations.

    Reward / termination:

    * If reward_matches == true AND done_matches == true, explicitly say they match and DO NOT suggest changes to reward or termination.

    Action space:

    * If GT uses Box(low, high, shape): align bounds and expose them via env.action_space or a getter; clamp only at action ingestion or observation, not inside the integrator.
    * If GT uses Discrete(n): actions are integer indices in [0, n-1]; expose n; if indices map to torques/commands, keep the mapping table consistent; do not float-clip discrete actions.
    * If GT action-space info is missing, skip action-space checks.

    State vs observation:

    * Prefer state_matches; if only observation signals exist, use obs_matches and state this explicitly.
    * If clipping or angle normalization occurs inside the integrator step, prefer moving it to the observation path unless GT specifies otherwise.

    Integrator / dt:

    * If integrator method or dt differs from GT and state mismatches persist, acknowledge this and consider aligning them.

    Multiple transitions:

    * When multiple transitions are reported, base success on an aggregate (e.g., ≥ 95% of transitions matched or high success_rate).

    </Rubric>

    <Procedure>
    1) Static review: action handling and bounds, clipping/normalization placement, integrator and dt, observation construction.
    2) Execute: call play_env once.
    3) Diagnose: reconcile play_env signals with the code; explicitly mention reward/done matches and state/observation matches; identify 1–2 most likely root causes.
    4) Suggest: propose 1–3 minimal patches targeting these root causes.

    <OutputFormat>
    Return exactly one <final> block containing a single JSON object:
    {{
    "success": true|false,
    "analysis": "<2–4 sentences summarizing what happened and why; mention matches/mismatches explicitly>",
    "suggest_fix": "- bullet 1\\n- bullet 2\\n- bullet 3 (optional)"
    }}
    No extra text outside <final>. No additional code fences.
    </OutputFormat>
    """.strip()


    def build_pytest_env_prompt(self, code: str, code_file_path: str) -> str:
        return f"""

    PYTEST_EVAL

    <Task Description>
    {self.task_describe}
    </Task Description>

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
    - Sanity: class Environment can be imported and instantiated, e.g., Environment(seed=0).
    - Contract:
    1) set_state accepts list/tuple/ndarray of the same logical content (convert to canonical).
    2) step(action) returns a 3-tuple: (observation, reward, done) with expected types/shapes.
    3) Determinism: with the same seed and same initial state, the first step with the same action yields identical outputs.
    4) Action space validation: actions within bounds are accepted, out-of-bounds actions are handled gracefully.
    5) Observation space validation: observations match declared space bounds and shapes.
    6) State space consistency: internal state dimensions match expected environment specifications.
    - Acceptance: success iff pytest exit_code == 0 (all tests pass).
    </TestPlan>


    <ReportingGuidelines>
    - Summarize pytest results in 2–4 sentences; mention the first failing nodeid/assert if any.
    - Provide a brief contract coverage assessment and the most probable root cause for failures.
    - If failing, add 1–3 concise actionable fixes (no long logs).
    </ReportingGuidelines>


    <OutputFormat>
    Return exactly one <final> block containing a single JSON object that matches PytestReport:
    {{
    "success": true|false,
    "analysis": "<2–4 sentence summary/diagnosis>",
    "suggest_fix": "<optional 1–3 bullets with minimal actionable changes>"
    }}
    No extra text outside <final>. No additional code fences.


    <final>
    {{ "success": false, "code_result": "", "analysis": "", "suggest_fix": "" }}
    </final>
    </OutputFormat>
    """.strip()



def _sanitize_code_text(code: str) -> str:
    s = code if isinstance(code, str) else str(code)
    i1 = s.find("<entrypoint_code>")
    if i1 != -1:
        i1 += len("<entrypoint_code>")
        i2 = s.find("</entrypoint_code>", i1)
        if i2 != -1:
            s = s[i1:i2]
    s = s.replace("<final>", "").replace("</final>", "")
    s = s.strip()
    s = re.sub(r"^```(?:python)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()

def generate_mcts_code(
    benchmark_type: str,
    environemnt: str,
    task_describe: str,
    results_base_dir: str = "./result",
    simulator = None,
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
        simulator,
        enable_research=enable_research,
        enable_player=enable_player,
        enable_pytest=enable_pytest
    )

    mcts_prompt = MctsPrompt(environemnt, task_describe,simulator)
    
    code = agent2world_gen_cwmb_code(
        agent2world_agents,
        mcts_prompt,
        enable_research=enable_research,
        enable_player=enable_player,
        enable_pytest=enable_pytest
    )
    
    return _sanitize_code_text(code)
