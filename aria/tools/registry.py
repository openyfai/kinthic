"""
Tool Registry. Manages tool registration and execution routing.

Security: All tool arguments are validated against the tool's schema
before execution to prevent injection of unexpected parameters.
"""

from __future__ import annotations

import json

from aria.models.schemas import ToolCall, ToolResult
from aria.tools.base import BaseTool
from aria.tools.search import WebSearchTool
from aria.tools.file_reader import FileReaderTool
from aria.tools.code_editor import CodeEditorTool, ApplyEditTool
from aria.utils.logger import setup_logger

log = setup_logger("aria.tools.registry")


class ToolRegistry:
    """Holds available tools and executes them based on ToolCalls."""
    
    def __init__(self):
        self.tools: dict[str, BaseTool] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register the default Phase 5 tools."""
        self.register(WebSearchTool())
        self.register(FileReaderTool())
        self.register(CodeEditorTool())
        self.register(ApplyEditTool())

    def register(self, tool: BaseTool) -> None:
        """Register a new tool."""
        self.tools[tool.name] = tool
        log.info(f"Registered tool: {tool.name}")

    def get_system_prompt_appendix(self) -> str:
        """Returns the formatted documentation of all tools for the LLM prompt."""
        if not self.tools:
            return "No tools available."
            
        docs = "AVAILABLE TOOLS:\n"
        for tool in self.tools.values():
            docs += tool.get_prompt_description() + "\n"
            
        return docs

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a ToolCall and return a ToolResult."""
        tool = self.tools.get(call.tool_name)
        if not tool:
            log.warning(f"Attempted to call unknown tool: {call.tool_name}")
            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome="Error: Tool not found in registry.",
                success=False,
                error="Tool not found"
            )

        # ── Parse arguments ──────────────────────────────────────
        args_dict = {}
        if isinstance(call.arguments, str):
            try:
                args_dict = json.loads(call.arguments)
            except json.JSONDecodeError:
                return ToolResult(
                    tool_name=call.tool_name,
                    actual_outcome="Error: Failed to parse arguments as JSON.",
                    success=False,
                    error="JSON parse error"
                )
        elif isinstance(call.arguments, dict):
            args_dict = call.arguments

        # ── Validate arguments against schema ────────────────────
        # Only allow keys defined in the tool's schema
        allowed_keys = set(tool.schema.keys()) if tool.schema else set()
        unexpected_keys = set(args_dict.keys()) - allowed_keys
        if unexpected_keys:
            log.warning(
                f"Tool {call.tool_name}: rejected unexpected args: {unexpected_keys}"
            )
            # Strip unexpected keys rather than crash
            args_dict = {k: v for k, v in args_dict.items() if k in allowed_keys}

        log.info(f"Executing {call.tool_name} with args: {list(args_dict.keys())}")

        try:
            outcome = await tool.execute(**args_dict)
            # If the outcome string starts with "Error:", we consider it a failure
            success = not outcome.startswith("Error:")
            
            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome=outcome,
                success=success,
                error=outcome if not success else None
            )
        except Exception as e:
            log.error(f"Tool {call.tool_name} crashed: {e}")
            return ToolResult(
                tool_name=call.tool_name,
                actual_outcome=f"Error executing tool: internal error occurred.",
                success=False,
                error="Internal tool execution error"
            )
