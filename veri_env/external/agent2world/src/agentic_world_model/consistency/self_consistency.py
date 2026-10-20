from __future__ import annotations
from typing import List, Dict
from loguru import logger
import io
import tokenize
from src.prompts import GenCodePromptTemplateDict
from src.agentic_world_model.utils import extract_all_finals
from src.utils.llm import call_llm
import re

def _build_generate_prompt(task_describe: str) -> str:
    return f"""
<Task Description>
{task_describe}
</Task Description>

Return exactly one <final> block containing one fenced Python code block.
""".strip()

def _generate_once(task_describe: str, temperature: float, max_tokens: int) -> str:
    prompt = _build_generate_prompt(task_describe)
    resp_text = call_llm(
        prompt,
        system_prompt="You are a helpful assistant that generates code.",
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return _extract_code(resp_text)

def _extract_code(resp) -> str:
    s = resp if isinstance(resp, str) else str(resp)
    m = re.findall(r"```python\s*([\s\S]*?)\s*```", s, flags=re.IGNORECASE)
    if not m:
        return resp
    return m[-1].strip()

def _strip_python_comments(code: str) -> str:
    out = io.StringIO()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        for tok_type, tok_str, _, _, _ in tokens:
            if tok_type == tokenize.COMMENT:
                continue
            out.write(tok_str)
        return out.getvalue()
    except Exception:
        return code

def _normalize_for_vote(code: str) -> str:
    stripped = _strip_python_comments(code)
    lines = [l.rstrip() for l in stripped.splitlines() if l.strip()]
    return "\n".join(lines)

def self_consistency(task_describe: str) -> str:
    logger.info("Self-Consistency generation started")
    n = 5
    codes: List[str] = []
    for _ in range(n):
        try:
            code = _generate_once(task_describe, temperature=0.5, max_tokens=20000)
        except Exception as e:
            logger.error(f"generation error: {e}")
            code = ""
        if code:
            codes.append(code)
    if not codes:
        return ""
    counter: Dict[str, int] = {}
    index_map: Dict[str, int] = {}
    for idx, c in enumerate(codes):
        key = _normalize_for_vote(c)
        counter[key] = counter.get(key, 0) + 1
        if key not in index_map:
            index_map[key] = idx
    best_key = max(counter.items(), key=lambda kv: (kv[1], len(kv[0])))[0]
    selected = codes[index_map[best_key]]
    return selected