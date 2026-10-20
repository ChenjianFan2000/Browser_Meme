from __future__ import annotations
from typing import List, Tuple
from loguru import logger
from src.prompts import GenCodePromptTemplateDict
from src.agentic_world_model.utils import extract_payload_from_response
from src.utils.llm import call_llm
import re
import time

def _build_generate_prompt(task_describe: str) -> str:
    return f"""
<Task Description>
{task_describe}
</Task Description>

Return exactly one <final> block containing one fenced Python code block.
""".strip()

def _build_score_prompt(task_describe: str, code: str) -> str:
    return f"""
<Task>
{task_describe}
</Task>

<CandidateCode>
```python
{code}
```
</CandidateCode>

Assess how well the code satisfies the task, correctness, completeness, single-file constraints, and portability. Return exactly one <final> JSON object: {{"score": <0-100 integer>, "analysis": "short"}}.
""".strip()

def _generate_once(task_describe: str, temperature: float, max_tokens: int) -> str:
    prompt = _build_generate_prompt(task_describe)
    t0 = time.time()
    resp_text = call_llm(
        prompt,
        system_prompt="You are a helpful assistant that generates code.",
        max_tokens=max_tokens,
        temperature=temperature,
    )
    logger.info(f"_generate_once time: {time.time() - t0:.3f}s")
    return _extract_code(resp_text)

def _extract_code(resp) -> str:
    s = resp if isinstance(resp, str) else str(resp)
    m = re.findall(r"```python\s*([\s\S]*?)\s*```", s, flags=re.IGNORECASE)
    if not m:
        return resp
    return m[-1].strip()

def _score(task_describe: str, code: str) -> Tuple[int, str]:
    system = GenCodePromptTemplateDict.build()
    prompt = _build_score_prompt(task_describe, code)
    t0 = time.time()
    resp_text = call_llm(
        prompt,
        system_prompt=system,
        max_tokens=512,
        temperature=0.0,
    )
    logger.info(f"_score time: {time.time() - t0:.3f}s")
    obj = extract_payload_from_response(resp_text, final_mode="last", fence_mode="last", auto_json=True)
    try:
        score = int(obj.get("score", 0)) if isinstance(obj, dict) else 0
        analysis = obj.get("analysis", "") if isinstance(obj, dict) else ""
        return score, analysis
    except Exception:
        return 0, ""

def best_of_n(task_describe: str) -> str:
    logger.info("Best-of-N generation started")
    n = 1
    candidates: List[Tuple[str, int]] = []
    for _ in range(n):
        code = _generate_once(task_describe, temperature=0.7, max_tokens=9160)
        s, _ = _score(task_describe, code)
        candidates.append((code, s))
    best = max(candidates, key=lambda x: x[1])
    logger.info(f"Selected with score {best[1]}")
    return best[0]
