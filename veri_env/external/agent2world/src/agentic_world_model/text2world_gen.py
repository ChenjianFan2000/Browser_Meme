import os
import sys
from typing import Optional
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.insert(0, project_root)

from .agentic_world_framework import initialize_agent, agent2world_gen_pddl_code
from .utils import WorldModelPromptBase
 

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
class Text2WorldPrompt(WorldModelPromptBase):
    def __init__(self,task_id: str, task_describe: str):
        super().__init__(task_describe, final_language='pddl')
        self.task_id = task_id
        self.task_describe = task_describe

    def build_research_prompt(self) -> str:
        """
        Build a concise research report for PDDL domain modeling from the task description.
        """
        return f"""
Your task is to conduct comprehensive research for PDDL domain modeling to support the subsequent generation of a high-quality PDDL domain definition based on the planning task description provided below.

<Focus>
- Requirements actually needed (:strips, :typing, :negative-preconditions, :equality).
- Types policy (typed vs untyped) and naming conventions.
- Predicates: names and arities.
- Actions: names, parameters, preconditions, effects.
- Quality checklist: syntax, symbol consistency, completeness.
</Focus>

### Planning Task Description:
```markdown
{self.task_describe}
```

**Output Requirements**
Produce a concise research report that directly guides domain implementation. Output ONLY a research report—no code.

<OUTPUT FORMAT>
<final>
{{ "research_summary": "...", "implementation_spec": {{ "requirements": ["..."], "types": ["..."], "predicates": {{"name": arity}}, "actions": {{"name": {{"params": ["?x - type"], "preconditions": ["..."], "effects": ["..."]}}}} }}, "test_plan": {{ "sanity": ["domain parses"], "checks": ["predicates declared", "actions consistent", "requirements cover used features"] }} }}
</final>
### END
<OUTPUT FORMAT>

        """.strip()

    def build_gen_code_prompt(self, research_report, feedback):
        """
        Code generation prompt with PDDL implementation requirements,
        adapted from single_agent_code_gen prompt structure
        """
        if feedback:
            mode_header = f""" 
            Mode: debug (apply minimal fixes; keep API unchanged)
            {self.task_describe}

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

    PDDL_DOMAIN_GENERATION

    <Task>
    Your task is to generate a complete, syntactically correct PDDL domain definition based on the research report and task description. The PDDL domain you generate must strictly comply with the task description, especially the definitions of variable names and parameter names. When you need to make corrections, the modified PDDL domain must also strictly comply with the task description,
    especially the definitions of variable names and parameter names.
    </Task>

    {mode_header}

    <Workflow>
    1. **Deconstruct Specification:** Carefully review the `<Task Description>` and `<Research Report>` (for generate phase) or `<feedback>` (for fix phase) to fully understand the domain requirements, including entities, relationships, actions, and constraints.
    2. **Domain Analysis:** Identify all necessary PDDL components: domain name, requirements, types, predicates, and actions from the specification.
    3. **Predicate Design:** Define all predicates with correct arities and parameter types based on the domain entities and their relationships.
    4. **Action Modeling:** Design each action with proper parameters, preconditions, and effects that accurately reflect the domain dynamics.
    5. **Syntax Validation:** Use PDDL validation through the run_bash tool, ensure all PDDL syntax is correct, including proper parentheses, keywords, and structure.
    6. **Self-Correction Review:** Meticulously check that the generated PDDL domain fully complies with the `<Task Description>`, the `<Research Report>`, and all naming conventions using the `<QualityChecklist>`.
    7. **Finalize Output:** Present the complete, syntactically correct, and runnable PDDL domain in the specified format.
    </Workflow>

    <ImplementationRequirements>
    Generate a complete PDDL domain definition meeting the following requirements:
    - Complete PDDL domain structure with proper syntax including:
        - (define (domain domain-name))
        - (:requirements ...) section with appropriate PDDL requirements
        - (:types ...) section if using typed predicates
        - (:predicates ...) section with all necessary predicates
        - (:action ...) sections for all described actions
    - Each action must include:
        - :parameters with proper variable typing
        - :precondition specifying when the action can be executed
        - :effect specifying the changes caused by the action
    - All predicates must be properly defined with correct arity
    - Domain must comprehensively cover all aspects described in the task
    - Use naming conventions that completely match the task description for predicates and actions
    </ImplementationRequirements>


        
    <PDDL Syntax Validation and Self-Testing>
    You have access to PDDL validation utilities via the run_bash tool.

    **HOW TO TEST (Pre-configured Test Code)**
    We have already provided and placed the test code for you. To validate your PDDL domain, simply run:
    - `python test/pddl_validator.py path/to/domain.pddl`

    **DELIVERABLE (No Extra Python Code)**
    - Return a single, complete PDDL **domain** inside a fenced code block marked as `pddl`.
    - Do NOT include Python, pseudocode, or partial fragments. Only provide the full PDDL domain.

    **Self-Validation (One-Pass Rule)**
    Before submitting your final answer:
    1) Save your PDDL to a file (e.g., `domain.pddl`).
    2) Run `python test/pddl_validator.py domain.pddl` using run_bash.
    3) Only return once the validator prints `PDDL Validation: True` and `PDDL domain is syntactically correct!`.
    4) If validation fails, fix the PDDL and re-run until it passes.

    **Validation Guidelines**
    • Syntax Validation — The domain must parse without errors using Tarski `PDDLReader` as invoked by `test/pddl_validator.py`.
    </PDDL Syntax Validation and Self-Testing>

    <Output Format>
    <final>
    <code_file_path>domain.pddl</code_file_path>
    <pddl_domain>
(define (domain your-domain-name)
  ;;; fill with your generated PDDL domain
)
    </pddl_domain>
    </final>
    </Output Format>
""".strip()


    def build_play_env_prompt(self, code, code_file_path: str) -> str:
        """
        Static PDDL domain review prompt (no tool execution)
        """
        return f"""

<Task>
Review the PDDL domain and propose minimal fixes. Optionally outline a minimal, reachable problem instance (objects, init, goal). Do not execute tools.
</Task>

<Task_Description>
{self.task_describe}
</Task_Description>     

<CodeArtifact path="{code_file_path}">
```pddl
{code}
```
</CodeArtifact>

<Workflow>
1. Build & save problem.pddl
From the CodeArtifact and Task_Description (and <InstanceSpec> if provided), generate a minimal, reachable instance: detect typed vs untyped (add pseudo-type facts in :init if untyped), choose a small object set, define connectivity (add symmetric edges if needed), ensure at least one valid action at t=0 (e.g., open a neighbor or place required resources), set an achievable :goal, and save the problem using {{ProblemTemplate}} to domain_dir/file_out.

2. Static analysis only (no execution)
   Identify likely issues preventing reachability or correctness; suggest precise fixes.

3. Recommendations
   Provide 1–3 concise, actionable fixes (e.g., declare :negative-preconditions when using (not ...); add symmetric connectivity; include required pseudo-type facts in :init).

4. Recommendations
   Output concise, actionable fixes (e.g., declare \:negative-preconditions when actions use (not ...), add symmetric connectivity, initialize required open/locked states and key/lock mappings/resources in \:init, and for untyped domains include (place ...), (key ...), (shape ...) in \:init).

   </Workflow>

<ProblemSpec id="PDDLProblemSpec">
  <Guidance>
  Use this spec to produce a minimal, reachable problem instance for the given domain.
  - domain_name: MUST equal the domain’s (:domain ...) in the CodeArtifact.
  - objects_typed / objects_untyped: For typed domains, list "name - type"; for untyped, list symbols and remember to add pseudo-type facts (e.g., (place ...), (key ...), (shape ...)) in :init if actions check them.
  - connectivity: Provide movement relations (e.g., conn/adjacent). Add symmetric edges if two-way motion is intended.
  - init_facts: Include the robot start, item placements, key/lock mappings, locked/open states, arm/hand states, and any pseudo-type facts (untyped).
  - goal: A single literal or (and ...) that is achievable from :init and exercises key mechanics.
  - file_out: Output filename; write the file next to the domain.
  </Guidance>

  <Template>
  <!-- When emitting the problem, wrap the file in a NewFile tag:
       <NewFile path="domain_dir/file_out">
       ...problem content...
       </NewFile>
  -->
  ```pddl
  (define (problem <auto_name>)
    (:domain <must_match_domain_name>)
    (:objects
      <objects_here>
    )
    (:init
      <init_facts_here>
    )
    (:goal
      <goal_here>
    )
  )
  ```
  </Template>

  <Fields>
  domain_name:           # MUST match (:domain ...) in the CodeArtifact
  objects_typed:         # e.g., "p1 p2 p3 - place; kA - key; sA - shape" (leave empty if untyped)
  objects_untyped:       # e.g., "p1 p2 p3 kA sA" (leave empty if typed)
  connectivity:          # e.g., "conn: (p1 p2),(p2 p1),(p2 p3),(p3 p2)" or "adjacent: (a1 a2),(a2 a1)"
  init_facts:            # Start states, resources, mappings, open/locked, plus pseudo-types for untyped
  goal:                  # A single goal or (and ...)
  file_out: problem1.pddl
  </Fields>
</ProblemSpec>

<OutputFormat>
Return exactly one <final> block containing a single JSON object that matches PlayReport:
{{
  "success": true|false,
  "analysis": "<2–4 sentences summarizing what happened and why; mention matches/mismatches explicitly>",
  "suggest_fix": "- bullet 1\n- bullet 2\n- bullet 3 (optional)"
}}
No extra text outside <final>. No additional code fences.
</OutputFormat>

        """.strip()

    def build_pytest_env_prompt(self, code: str, code_file_path: str) -> str:
        """
        Validation prompt using Tarski PDDLReader validation logic from single-agent implementation
        """
        return f"""

    PYTEST_EVAL

    <Role>
    Generate one pytest file to parse the provided PDDL domain and validate the semantics accuracy and completeness with task description. Tests must read the PDDL as plain text and use the TestTemplate, do not write additional tests yourself.
    </Role>

    <TaskDescription>
    ```pddl
    {self.task_describe}
    ```
    </TaskDescription>
    

<CodeArtifact path="{code_file_path}">
```pddl
{code}
```
</CodeArtifact>

    <ExecutionPolicy> 
    - Do not modify the student's source file. 
    - Create EXACTLY ONE pytest file at "tests/test_env.py" via file_tool('save'); do not save again. 
    - Read the PDDL as PLAIN TEXT from "{code_file_path}" (no importlib; no markdown extraction). 
    - Run tests EXACTLY ONCE with run_bash('python -m pytest -q --tb=short tests/test_env.py', env_requirements=["tarski","pytest"]); capture exit_code, duration, and stdout/stderr tail.
    </ExecutionPolicy>

    <TestPlan>
    **PDDL Validation Requirements**

    You must perform PDDL validation using the same validation utilities as the following validation code pattern:

    **CRITICAL REQUIREMENT: Complete Executable Code**
    You MUST **ALWAYS** provide **COMPLETE EXECUTABLE CODE** for validation, including:
    - All required import statements
    - All function definitions (extract_pddl, validate_pddl_domain, parse_actions, parse_predicates)
    - Your complete PDDL domain definition
    - Complete validation call code

    **NO OMISSIONS ALLOWED. NO CODE FRAGMENTS. Each execution must be independent and complete.**
    
    </TestPlan>

    <TestTemplate>
    ```python
    # All of the following code must be included in each verification
    import re
    from tarski.io import PDDLReader
    from tarski.syntax.formulas import *
    import traceback

    def extract_pddl(text):
        if not isinstance(text, str):
            raise TypeError("Input 'text' must be a string")
        if not text.strip():
            raise ValueError("Input 'text' cannot be empty")

        pattern = r"```pddl\\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches == []:
            pattern = r"```\\n(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)

        if not matches:
            raise ValueError("No PDDL code block found in the text")

        pddl = max(matches, key=len).replace('```pddl', '').replace('```', '').strip()
        if not pddl:
            raise ValueError("Extracted PDDL code is empty")

        return pddl

    def validate_pddl_domain(pddl_domain, raise_on_error=True):
        try:
            reader = PDDLReader(raise_on_error=raise_on_error)
            reader.parse_domain_string(pddl_domain)
            return True, 'Success'
        except Exception as e:
            exception_type = type(e).__name__
            traceback_info = traceback.format_exc()
            error_message = f"{{exception_type}}: {{str(e)}}"
            return False, error_message

    def parse_actions(pddl_domain):
        reader = PDDLReader(raise_on_error=True)
        reader.parse_domain_string(pddl_domain)
        return reader.problem.actions

    def parse_predicates(pddl_domain):
        reader = PDDLReader(raise_on_error=True)
        reader.parse_domain_string(pddl_domain)
        predicate_map = {{}}
        for pred in reader.problem.language.predicates:
            if str(pred.symbol) not in ['=', '!=']:
                predicate_map[str(pred.symbol)] = pred.arity
        return predicate_map

    # Validate syntax
    is_valid, message = validate_pddl_domain(your_pddl_domain)
    print(f"PDDL Validation: {{is_valid}}")
    if not is_valid:
        print(f"Error: {{message}}")
    else:
        print("PDDL domain is syntactically correct!")

        # Parse and display domain components
        try:
            actions = parse_actions(your_pddl_domain)
            predicates = parse_predicates(your_pddl_domain)
            pred_actions = {{k:{{'params': self._preprocess([f"{{p.symbol}}" for p in v.parameters]),
                             'preconds':self._preprocess([x.strip() for x in str(v.precondition)[1:-1].split('and')]),
                             'effect':self._preprocess([str(x) for x in v.effects])}} for k, v in pred_actions.items()}}
            print(f"Actions found: {{parse_actions}}")
            print("Predicates found", [f"{{k}}_{{v}}" for k, v in predicates.items()])
        except Exception as e:
            print(f"Error parsing domain components: {{e}}")
    ```
    </TestTemplate>
    
    <Validation Guidelines>
    Ensure your domain passes these checks with task description:
    - Syntax Validation – Domain must parse without syntax errors using Tarski PDDLReader
    - Acceptance: success iff pytest exit_code == 0 (all tests pass).
    - Completeness Check – All actions and predicates mentioned in the task description must be defined
    - Action Integrity – Each action must have proper parameters, preconditions, and effects
    - Predicate Consistency – All predicates used in actions must be declared in the predicates section
    - Type Consistency – If using typing, all variables must be properly typed
    - Requirements Compatibility – All PDDL features used must be declared in requirements section
    </Validation Guidelines>
    
    <ReportingGuidelines>
    - Summarize pytest results in 2–4 sentences; mention the first failing nodeid/assert if any.
    - Provide a brief validation coverage assessment and the most probable root cause for failures.
    - If failing, add 1–3 concise actionable fixes (no long logs).
    - If semantic detection finds an issue, please describe it in detail.
    </ReportingGuidelines>

<OutputFormat>
Return exactly one <final> block containing a single JSON object matching PytestReport:
{{
  "success": true|false,
  "analysis": "<2–4 sentences summarizing validation and issues>",
  "suggest_fix": "<optional 1–3 bullets>"
}}
No extra text outside <final>.
""".strip()

def generate_text2world_code(
    task_id: str,
    benchmark_type: str,
    task_describe: str,
    results_base_dir: str = "./result",
    # Ablation study control parameters
    enable_research: bool = True,
    enable_player: bool = True,
    enable_pytest: bool = True,
    strategy: str = "agentic",
    model: Optional[str] = None,
) -> str:
    """
    Orchestrate the multi-agent pipeline for text2world PDDL generation:
      1. Research PDDL domain patterns
      2. Generate PDDL domain
      3. Test with PDDLGym
      4. Validate with Tarski
    Returns the finalized PDDL domain code.
    """

    _ = (strategy, model)
    agent2world_agents = initialize_agent(
        benchmark_type,
        results_base_dir,
        simulator=None,
        enable_research=enable_research,
        enable_player=enable_player,
        enable_pytest=enable_pytest
    )

    text2world_prompt = Text2WorldPrompt(task_id,task_describe)

    code = agent2world_gen_pddl_code(
        agent2world_agents,
        text2world_prompt,
        task_describe,
        enable_research=enable_research,
        enable_player=enable_player,
        enable_pytest=enable_pytest
    )

    return code
