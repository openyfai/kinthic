"""
Base Tool Interface.
"""

from __future__ import annotations

import inspect
from pydantic import BaseModel

class BaseTool:
    """Abstract base class for all ARIA tools."""
    
    name: str = "base_tool"
    description: str = "Base description."
    
    # We will use this schema to inform the LLM how to call the tool
    schema: dict = {}

    async def execute(self, **kwargs) -> str:
        """
        Execute the tool with the given arguments.
        Must return a string representing the outcome (success or error details).
        """
        raise NotImplementedError("Tools must implement the execute method.")

    @classmethod
    def get_prompt_description(cls) -> str:
        """Formats the tool for the system prompt."""
        return f"- **{cls.name}**: {cls.description}\n  Args: {cls.schema}"
