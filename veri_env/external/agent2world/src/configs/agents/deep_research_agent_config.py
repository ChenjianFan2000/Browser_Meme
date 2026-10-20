# src/configs/agents/deep_research_agent_config.py
from dataclasses import dataclass, field
from src.configs.agents.base_config import AgentConfig

@dataclass
class DeepResearchAgentConfig(AgentConfig):
    """Concrete config with sensible defaults for a DeepResearchAgent."""
    agent_type = "deep_research"

    @classmethod
    def default(cls) -> "DeepResearchAgentConfig":
        from src.prompts import DeepResearchPromptTemplateDict
        # You can pass *string values*; Pydantic will coerce them to enums,
        # or you can import the enums here and pass the enum members explicitly.
        return cls(
            system_message=DeepResearchPromptTemplateDict.build(),
            model_platform=cls.PlatformEnum.OPENAI,
            model_type=cls.ModelEnum.GPT_4O_MINI,
            model_params={"temperature": 0.0},
            toolkit_imports=["src.toolkits:WebSearchToolkit"],
            toolkit_kwargs={},
            auto_save=True,
            results_base_dir="./results/deep_research",
        )
    