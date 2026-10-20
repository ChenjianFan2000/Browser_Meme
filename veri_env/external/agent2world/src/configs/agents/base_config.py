# src/configs/agents/base_config.py
from typing import Any, Dict, List, Optional, ClassVar
from pydantic import BaseModel, Field
from typing_extensions import Literal
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class AgentConfig():
    """
    Serializable config for building an Agent.
    """
    from src.types.enums import ModelPlatformType, ModelType
    PlatformEnum: ClassVar[type[ModelPlatformType]] = ModelPlatformType
    ModelEnum: ClassVar[type[ModelType]] = ModelType
    # Choose one of the two built-in agents
    agent_type: Literal["chat", "deep_research","player"] = "chat"

    # Optional hard override (advanced). If set, it wins over agent_type.
    # Format: "package.module:ClassName"
    agent_cls_path: Optional[str] = None

    # Core prompt & model
    system_message: Optional[str] = None
    model_platform: ModelPlatformType = None
    model_type: ModelType = None
    model_params: Dict[str, Any] = Field(default_factory=dict)

    # Toolkits to load dynamically by class path
    toolkit_imports: List[str] = Field(default_factory=list)
    toolkit_kwargs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # Persistence & misc
    auto_save: bool = True
    results_base_dir: str = "./results/"
    
    @abstractmethod
    def default(cls) -> "AgentConfig":
        pass
    