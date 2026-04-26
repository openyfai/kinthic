# ARIA Phase 5: Tool Use + Embodiment Simulation Implementation Plan

This document outlines the architecture for Phase 5. Up to this point, ARIA has been a "brain in a vat." Phase 5 gives her hands and eyes. She will be able to plan tool usage, execute external actions (like web searches), observe the results, and update her internal World Model based on whether reality matched her predictions.

## 1. Core Concept: The Action-Outcome Loop

We will introduce a `ToolRegistry` and modify the `CognitiveLoop` to support a multi-step execution path:
1. **Plan**: In her initial `CognitiveResponse`, ARIA can optionally output a list of `ToolCall` objects. Crucially, she must explicitly state her `expected_outcome` before the tool is run.
2. **Execute**: The `CognitiveLoop` pauses reasoning, executes the requested tools via the `ToolRegistry`, and captures the `actual_outcome`.
3. **Observe & Recover**: The results are fed back into ARIA in a second pass. 
   - If the tool succeeded, she incorporates the facts into her final answer.
   - If the tool failed, she diagnoses the error and either replans or apologizes.
4. **Learn**: The delta between her `expected_outcome` and `actual_outcome` forms a learning signal, which is logged to the database.

## 2. Schema Evolution (`aria/models/schemas.py`)

New data models for structured tool usage.

```python
class ToolCall(BaseModel):
    """ARIA's intent to use a tool."""
    tool_name: str = Field(description="The exact name of the tool to use")
    arguments: dict[str, str] = Field(description="JSON arguments for the tool")
    expected_outcome: str = Field(description="What ARIA predicts will happen or what data will be returned")
    rationale: str = Field(description="Why this tool is necessary right now")

class ToolResult(BaseModel):
    """The actual result returned by the system."""
    tool_name: str
    actual_outcome: str
    success: bool
    error: str | None = None

class ActionLogEntry(BaseModel):
    """Persisted record of an action and its outcome."""
    id: str
    session_id: str
    turn_number: int
    tool_name: str
    arguments: str
    expected_outcome: str
    actual_outcome: str
    success: bool
    model_update: str = Field(description="How ARIA updated her world model based on the result")
    created_at: str
```

*Note: `CognitiveResponse` will be updated to include `tool_calls: list[ToolCall]`.*

## 3. Database Updates (`aria/storage/database.py`)

We need a table to persist the action logs for future analysis.

```sql
CREATE TABLE IF NOT EXISTS action_logs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    expected_outcome TEXT NOT NULL,
    actual_outcome TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    model_update TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

## 4. New Module: `aria/tools/registry.py` & Tool Implementations

We will create a structured tool interface.

```python
class BaseTool:
    name: str
    description: str
    schema: dict  # JSON schema of expected arguments

    async def execute(self, **kwargs) -> str:
        raise NotImplementedError

class WebSearchTool(BaseTool):
    # Uses duckduckgo-search to pull live facts from the internet
    ...

class FileReaderTool(BaseTool):
    # Reads local file contents securely
    ...

class ToolRegistry:
    # Registers tools and handles execution routing
    ...
```

## 5. Cognitive Loop Integration (`aria/core/cognitive_loop.py`)

The `process()` method will become an agentic loop:

```python
# Pseudo-code
draft = await self.gemini.think(...)

if draft.tool_calls:
    results = []
    for call in draft.tool_calls:
        result = await self.tool_registry.execute(call)
        results.append(result)
    
    # Second pass: feed results back in
    tool_context = format_results(results)
    final_response = await self.gemini.think(system_prompt + tool_context, user_input)
    
    await self._log_actions(draft.tool_calls, results, final_response.self_reflection)
    cognitive = final_response
else:
    # Proceed to Phase 3 Critique logic normally
    ...
```

## 6. Dependencies & UI

- **Dependency**: We will add `duckduckgo-search` to `pyproject.toml` so ARIA can search the web without needing paid API keys.
- **Terminal UI**: The Rich spinner will update to show: `🛠️ Executing Web Search...` -> `📊 Observing results...`
- **Commands**: `:tools` to see what capabilities are currently registered in her system.

---

### Implementation Steps
1. Add `duckduckgo-search` to `pyproject.toml`.
2. Add Schemas and `action_logs` SQLite table.
3. Build the `aria/tools/` directory (registry, search, file reader).
4. Integrate the execution loop into `CognitiveLoop.process()`.
5. Update Terminal UI to display tool execution states.
