# src/prompts/deep_research.py
from __future__ import annotations
from typing import Any, Optional

from .base import TextPrompt
from .template_dict import TextPromptDict
from src.types import RoleType  


class PlayerPromptTemplateDict(TextPromptDict):
    """
    Template dictionary for the Deep Research agent.

    - SYSTEM_PROMPT uses placeholders you can fill at runtime:
        {tools_guide}   -> Markdown/XML guide listing available tools and their usage
        {current_date}  -> Current date string (e.g., "2025-08-22")
        {session_id}    -> Optional session identifier (if you track sessions)

    Example:
        prompt = PlayerPromptTemplateDict.SYSTEM_PROMPT.format(
            tools_guide=my_tools_md,
            current_date="2025-08-22",
            session_id="20250822112233",
        )
    """

    SYSTEM_PROMPT = TextPrompt(
        """
You are an expert AI Code Debugging Assistant. Your goal is to iteratively improve a given piece of code. 
You will use tools to interact with the code, analyze the feedback, and then propose specific, actionable modifications to fix bugs or enhance functionality. 
You must base your analysis and suggestions strictly on the provided code and the feedback from your tools.
        """
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Pre-populate the dict with a default mapping so you can do:
            prompts = PlayerPromptTemplateDict()
            system = prompts[RoleType.ASSISTANT].format(...)
        """
        super().__init__(*args, **kwargs)
        self.update({RoleType.ASSISTANT: self.SYSTEM_PROMPT})

    @staticmethod
    def build(
        tools_guide: str = ""
    ) -> str:
        """
        Convenience helper to render the final system prompt as a plain string.
        Any omitted variable falls back to its {placeholder} (harmless).
        """
        return PlayerPromptTemplateDict.SYSTEM_PROMPT.format(
            tools_guide=tools_guide
        )