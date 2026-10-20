# -*- coding: utf-8 -*-
"""
Unified Base Environment Template for AgentGen v2
===============================================

A minimal abstract base class template for creating environments.
This serves as the foundation that will be extended by generated environments.
The environment integrates with MCP (Model Context Protocol) servers for tool simulation.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Tuple, Optional
from dataclasses import dataclass

# Gymnasium integration
try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    import gym as gym
    from gym import spaces

# MCP integration
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None


@dataclass
class ToolDefinition:
    """
    Tool definition structure for MCP tools.
    
    The environment generator will automatically determine the implementation approach:
    - Direct implementation: For tools that can be simulated with simple code logic
      (e.g., mathematical operations, file system operations, data transformations)
    - LLM simulation: For tools requiring external services or complex behavior
      (e.g., web search, maps API, proprietary data access, complex reasoning)
    
    The choice between direct vs LLM simulation should be made by the generator
    based on the tool's complexity and requirements.
    """
    name: str
    description: str
    parameters: Dict[str, Any]
    mcp_implementation: Optional[callable] = None  # MCP tool implementation function


class UnifiedBaseEnv(gym.Env, ABC):
    """
    Abstract base environment template for AgentGen v2.
    
    This minimal template should be extended by generated environments
    with specific tool implementations and task logic. It provides MCP server
    integration for simulated tool execution.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        tools: list[ToolDefinition],
        fs_root: str | Path | None = None,
        task_description: str = "",
        max_steps: int = 20,
        mcp_server_name: str = "simulation",
    ):
        """
        Initialize base environment.
        
        Args:
            tools: List of available MCP tools
            fs_root: Root directory for file system
            task_description: Description of the task
            max_steps: Maximum steps per episode
            mcp_server_name: Name for the MCP server instance
        """
        super().__init__()
        
        self.tools = tools
        self.fs_root = fs_root
        self.task_description = task_description
        self.max_steps = max_steps
        self.mcp_server_name = mcp_server_name
        
        # Environment state
        self.step_idx = 0
        self.execution_history = []
        
        # Initialize MCP server for tool simulation
        self.mcp_server = self._initialize_mcp_server()
        
        # Setup spaces
        self._setup_spaces()

    def _initialize_mcp_server(self) -> Optional[Any]:
        """
        Initialize MCP server with tool implementations.
        Should be implemented by subclasses to register MCP tools.
        
        Returns:
            MCP server instance or None if not available
        """
        if not FastMCP:
            return None
            
        mcp = FastMCP(self.mcp_server_name)
        # Subclasses should register their tool implementations here
        
        mcp._env = self
        return mcp

    def _setup_spaces(self):
        """Setup action and observation spaces."""
        # Action space: JSON string with tool call
        self.action_space = spaces.Text(max_length=2048)
        
        # Observation space: JSON strings
        self.observation_space = spaces.Dict({
            "task_description": spaces.Text(max_length=1024),
            "environment_state": spaces.Text(max_length=2048), 
            "execution_history": spaces.Text(max_length=4096),
            "available_tools": spaces.Text(max_length=2048),
        })

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        """Reset environment to initial state."""
        super().reset(seed=seed)
        
        self.step_idx = 0
        self.execution_history = []
        self._reset_environment_state()
        
        return self._get_observation(), {}

    def step(self, action: str) -> Tuple[Dict[str, str], float, bool, bool, Dict[str, Any]]:
        """
        Execute one step in the environment.
        
        Args:
            action: JSON string containing tool call {"tool": "tool_name", "args": {...}}
            
        Returns:
            observation, reward, terminated, truncated, info
        """
        self.step_idx += 1
        
        # Parse and execute action
        result = self._execute_action(action)
        self.execution_history.append(result)
        
        # Calculate reward
        reward = self._calculate_reward(result)
        
        # Check if done
        terminated = self._is_task_complete()
        truncated = self.step_idx >= self.max_steps
        
        info = {"step_result": result}
        
        return self._get_observation(), reward, terminated, truncated, info

    @abstractmethod
    def _execute_action(self, action: str) -> Dict[str, Any]:
        """
        Execute a tool action. Must be implemented by subclasses.
        
        Args:
            action: JSON string with tool call
            
        Returns:
            Dictionary with execution result
        """
        pass

    @abstractmethod
    def _calculate_reward(self, step_result: Dict[str, Any]) -> float:
        """
        Calculate reward for the step. Must be implemented by subclasses.
        
        Args:
            step_result: Result from _execute_action
            
        Returns:
            Reward value
        """
        pass

    @abstractmethod
    def _is_task_complete(self) -> bool:
        """
        Check if the task is complete. Must be implemented by subclasses.
        
        Returns:
            True if task is complete
        """
        pass

    @abstractmethod
    def _reset_environment_state(self):
        """Reset environment-specific state. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def _set_environment_state(self, initial_state: Dict[str, Any]):
        """
        Initialize the environment according to the given initial_state snapshot.

        Args: 
        initial_state: a dict describing the environment’s starting state,
                              e.g. files to create or key–value pairs to preload.
        """
        pass

    @abstractmethod
    def _get_environment_state(self) -> str:
        """
        Get current environment state as JSON string.
        Must be implemented by subclasses.
        
        Returns:
            JSON string representing current state
        """
        pass

    def _get_observation(self) -> Dict[str, str]:
        """Get current observation."""
        import json
        
        # Format available tools
        tools_info = [
            {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
            for tool in self.tools
        ]
        
        return {
            "task_description": self.task_description,
            "environment_state": self._get_environment_state(),
            "execution_history": json.dumps(self.execution_history[-5:]),  # Last 5 steps
            "available_tools": json.dumps(tools_info),
        }

    def render(self, mode="human"):
        """Render environment state."""
        if mode == "human":
            print(f"Step: {self.step_idx}/{self.max_steps}")
            print(f"Task: {self.task_description}")
            print(f"Available tools: {[t.name for t in self.tools]}")
            if self.execution_history:
                last_step = self.execution_history[-1]
                print(f"Last action: {last_step}")
            print("-" * 50)

    def close(self):
        """Clean up environment resources."""
        pass