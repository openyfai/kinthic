# UX Error States & User Survivability Audit

This audit evaluates the system's resilience to worst-case failures (database drops, AI model timeouts, unhandled crashes) from the user's perspective, mapping out what the user sees, identifying "Dead Ends," and pointing out telemetry blind spots.

---

## 1. The Silent Failure Trap

### 1.1 AI Model Timeouts & Provider Outages
- **Routing Layer Resilience**: [SmartRouter](file:///e:/AGI/silex/llm/smart_router.py) uses a fallback chain (`gemini` -> `anthropic` -> `openai` -> `ollama`). If the primary provider times out or throws an auth/rate-limit error (matching `_is_switchable_error`), the router catches it, logs a warning, and attempts the next provider in the chain.
- **Exhaustion Path**: If all providers in the chain fail or have no keys, a `RuntimeError("All providers exhausted...")` is raised.
- **TUI & CLI Presentation**: In CLI/TUI mode ([run.py](file:///e:/AGI/scripts/run.py)), the error is caught by `except Exception as exc:`, which displays a red warning toast to the user via `show_error(str(exc))`.
- **API & Dashboard Presentation**:
  - In [server.py](file:///e:/AGI/silex/api/server.py), the streaming generator catches the exception and yields a JSON error event: `{"type": "error", "data": {"message": str(exc)}}`.
  - In [TerminalOutput.tsx](file:///e:/AGI/kinthic-dashboard/src/components/TerminalOutput.tsx), if the stream fetch fails (rejects), the frontend catches it and appends a `Connection Error` message, resetting the loading state.
  - > [!CAUTION]
    > **The Fetch Status Code Hole (Silent Spinner)**: If the backend returns a non-2xx response status (such as `500 Internal Server Error` or `401 Unauthorized`) instead of dropping the network connection, `apiFetch` does NOT reject the promise. The frontend proceeds to read the body as a stream. Because the body is a simple JSON error payload and not an NDJSON stream with newline-delimited events, the parser loop does not emit any text, and the stream completes silently. The loader ceases spinning, but the user is left with a completely empty assistant response and zero indication of why it failed.

### 1.2 Database Connection Drops & Lockouts
- **State Persistence Boundary**: In `CognitiveLoop.process()` ([cognitive_loop.py](file:///e:/AGI/silex/core/cognitive_loop.py)), the database transaction block `async with self.db.transaction():` is placed **outside** the try-except reasoning block.
- **Crash Path**: If the SQLite connection drops, the disk fills up, or a transaction lock occurs during database flushes (storing memories, updating goals, writing causal edges), the exception propagates out of the cognitive loop entirely.
- **Dead End (CLI)**: In CLI mode, the loop catches the exception, prints it, and does a `continue`. While the CLI doesn't freeze, the database connection is not retried or re-established. Every subsequent turn will fail with the same database error, trapping the user in a broken session.
- **Dead End (API & Web Dashboard)**: The API endpoint returns a `500` error, which triggers the frontend "Silent Spinner" hole described above.

---

## 2. Graceful Degradation Analysis

### 2.1 Try/Catch Coverage in Core Orchestration
- **Reasoning Engine (LATS)**: Inside [cognitive_loop.py](file:///e:/AGI/silex/core/cognitive_loop.py), exceptions during the tree search are handled gracefully:
  - `json.JSONDecodeError` -> returns: `"I received a malformed response from my reasoning engine. Retrying on next turn."`
  - `ValueError` -> returns: `"I encountered a data validation error. Please try rephrasing your input."`
  - General `Exception` -> returns: `"I'm having trouble processing that right now. Your input was received and I'll try again on the next turn."`
  These messages are persisted as cognitive responses and displayed cleanly in the UI, preventing crashes.
- **Skill Loaders & Hot Reloading**: If skill loading fails (e.g., due to a corrupted markdown structure in `~/.kinthic/skills/`), the hot-reload command returns the raw exception string. While this exposes technical details, it gives the developer/user context to fix the markdown file.
- **Sandbox Orchestrator**: In [orchestrator.py](file:///e:/AGI/agent/orchestrator.py), if container warm pool warmups or executions fail:
  - `asyncio.TimeoutError` -> sets status to `FAILED` and records: `"Error: Worker execution timed out after X seconds."`
  - General `Exception` -> sets status to `FAILED` and records: `"Error: Worker execution error: {e}"`
  These errors are logged to the run's audit trail and written to `output.json`. However, this error state degrades silently from the user's perspective, as the web dashboard only displays chat turns and does not expose sandbox failure reasons.

---

## 3. Telemetry Gaps & Blind Spots

### 3.1 Unhandled Background Tasks
- **Fire-and-Forget Indexer**: Inside `CognitiveLoop.startup()`, workspace indexing runs as an unawaited task: `asyncio.create_task(asyncio.to_thread(indexer.run))`. If the indexer crashes due to filesystem permission issues, drive errors, or index corruption, it fails silently with no telemetry log or user alert.
- **Silent Fallback Reporting**: `SmartRouter.call_with_fallback()` handles provider failure cleanly for the user, but completely hides it from the telemetry trail. A primary provider (e.g., Gemini) could be failing 100% of the time due to credential expiration, and the system would silently fall back to expensive secondary providers (e.g., Anthropic) without alerting the operator or logging a critical alert.
- **TUI Process Crashes**: If the Node.js sub-process in `KinthicInkBridge.start()` crashes mid-run, Python falls back to Rich CLI mode. However, the crash details and exit codes are not reported to the gateway or log files, leaving the operator blind to the TUI's instability.
