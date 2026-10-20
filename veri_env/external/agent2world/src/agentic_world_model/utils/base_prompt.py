from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Dict

class WorldModelPromptBase(ABC):
    """
    Base scaffold for world-model prompt builders.
    - Provides helpers to render XML-like sections, shared quote policy,
      and a unified <final> fenced-code output contract.
    - Subclasses only implement the four builder methods.
    """

    def __init__(self, task_describe: str, *, final_language: str = 'python') -> None:
        self.task_describe = task_describe
        self.final_language = final_language

    # ---------- Shared blocks ----------

    @staticmethod
    def _section(title: str, body: str) -> str:
        title = title.strip()
        return f'<{title}>\n{body.strip()}\n</{title}>\n'

    @staticmethod
    def _quote_policy_block() -> str:
        return (
            '8) Quote Style\n'
            "    - Use single quotes for all outer Python string literals and f-strings.\n"
            "      Example: f'The value is {cfg[\"mode\"]}'\n"
            '    - Inside {...} expressions, dict/index keys, JSON fragments, or quoted substrings, use double quotes.\n'
            '      Examples: data[\'user\'] = record["id"]; json_str = \'{"ok": true}\'\n'
            '    - Prefer swapping outer/inner quote types over backslash escapes; escape only when unavoidable.\n'
        )

    def _final_code_output_contract(
        self,
        *,
        instruction_header: Optional[str] = None,
        include_entrypoint_hint: bool = True,
        language: Optional[str] = None,
    ) -> str:
        lang = (language or self.final_language or 'python').strip()
        header = (
            instruction_header.strip()
            if instruction_header
            else (
                'Once all research is summarised, all tests pass, and you are ready to deliver,\n'
                'return exactly one code block—that is, the complete environment\n'
                'implementation *plus* the required executable entry point.\n'
                '**Do NOT include any of your test code, fixtures, or helper scripts.**\n'
            )
        )
        body_lines = [
            '<OUTPUT FORMAT>',
            header,
            '<final>',
            f'```{lang}',
            '# Place your final, fully functional code here',
            '```',
            '',
            '</final>',
            '</OUTPUT FORMAT>',
        ]
        return '\n'.join(body_lines)

    # ---------- Abstract builders to implement ----------

    @abstractmethod
    def build_research_prompt(self) -> str:
        ...

    @abstractmethod
    def build_gen_code_prompt(self,research_report,feedback) -> str:
        ...

    @abstractmethod
    def build_play_env_prompt(self,code,code_file_path) -> str:
        ...

    @abstractmethod
    def build_pytest_env_prompt(self,code,code_file_path) -> str:
        ...
