import json
import re
from typing import Any, Dict

from src.utils.llm import call_llm


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


def _extract_json(text: str) -> Dict[str, Any]:
    s = text.strip()
    i1 = s.find("<final>")
    if i1 != -1:
        i1 += len("<final>")
        i2 = s.find("</final>", i1)
        if i2 != -1:
            s = s[i1:i2]
    try:
        return json.loads(s)
    except Exception:
        try:
            m = re.search(r"\{[\s\S]*\}", s)
            return json.loads(m.group(0)) if m else {}
        except Exception:
            return {}


def _build_generate_prompt(task_describe: str) -> str:
    return f"""
{task_describe}

<Workflow>
1. Deconstruct the specification and plan the Environment class.
2. Implement a complete single-file Python class `Environment`.
3. Ensure deterministic seeding and canonical input handling.
4. Return only the final code using the output format.
</Workflow>

<ImplementationRequirements>
• Single-file Python with class `Environment`
• Methods:
  - __init__(self, seed: int | None = None)
  - reset(self, seed: int | None = None) -> ndarray
  - set_state(self, state)
  - step(self, action) -> tuple[ndarray, float, bool]
• No external dependencies except Python stdlib and NumPy
• Validate inputs and keep computation efficient
• Deterministic behavior with a fixed seed
</ImplementationRequirements>

<Output Format>
<final>
<code_file_path>
environment.py
</code_file_path>
<entrypoint_code>
```python
# code
```
</entrypoint_code>
</final>
""".strip()


def _build_judge_prompt(task_describe: str, code: str) -> str:
    return f"""
<Task Description>
{task_describe}
</Task Description>

<CodeArtifact>
```python
{code}
```
</CodeArtifact>

Analyze if the code satisfies the task. Choose one action: "fix" or "improve".
Return exactly one <final> block containing one JSON object with keys:
{{"success": true|false, "action": "fix"|"improve", "feedback": "short guidance"}}

<final>{{"success": false, "action": "fix", "feedback": "..."}}</final>
""".strip()


def _build_fix_prompt(task_describe: str, code: str, feedback: str) -> str:
    return f"""
<Task Description>
{task_describe}
</Task Description>

<ExistingCode>
```python
{code}
```
</ExistingCode>

<Feedback>
{feedback}
</Feedback>

Return only the corrected single-file code in the output format.

<Output Format>
<final>
<code_file_path>
environment.py
</code_file_path>
<entrypoint_code>
```python
# code
```
</entrypoint_code>
</final>
""".strip()


def _build_improve_prompt(task_describe: str, code: str, feedback: str) -> str:
    return f"""
<Task Description>
{task_describe}
</Task Description>

<ExistingCode>
```python
{code}
```
</ExistingCode>

<Feedback>
{feedback}
</Feedback>

Return only the improved single-file code in the output format.

<Output Format>
<final>
<code_file_path>
environment.py
</code_file_path>
<entrypoint_code>
```python
# code
```
</entrypoint_code>
</final>
""".strip()


def generate_code(task_describe: str) -> str:
    prompt = _build_generate_prompt(task_describe)
    out = call_llm(prompt, max_tokens=20000, temperature=0.5)
    return _sanitize_code_text(out)


def judge_code(task_describe: str, code: str) -> Dict[str, Any]:
    prompt = _build_judge_prompt(task_describe, code)
    out = call_llm(prompt, max_tokens=1024, temperature=0.0)
    return _extract_json(out)


def fix_code(task_describe: str, code: str, feedback: str) -> str:
    prompt = _build_fix_prompt(task_describe, code, feedback)
    out = call_llm(prompt, max_tokens=20000, temperature=0.2)
    return _sanitize_code_text(out)


def improve_code(task_describe: str, code: str, feedback: str) -> str:
    prompt = _build_improve_prompt(task_describe, code, feedback)
    out = call_llm(prompt, max_tokens=20000, temperature=0.3)
    return _sanitize_code_text(out)


def run_gif_mcts_simple(task_describe: str, iterations: int = 5) -> str:
    code = generate_code(task_describe)
    for _ in range(max(1, iterations)):
        judge = judge_code(task_describe, code)
        if judge.get("success") is True:
            confirm = judge_code(task_describe, code)
            if confirm.get("success") is True:
                break
        action = judge.get("action") or "fix"
        feedback = str(judge.get("feedback") or "")
        if action == "improve":
            code = improve_code(task_describe, code, feedback)
        else:
            code = fix_code(task_describe, code, feedback)
    return code
