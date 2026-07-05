# Deep Audit Report: API & Routing

This report evaluates the API endpoints, HTTP routing, request lifecycles, and concurrency patterns in the local gateway server.

---

## 1. Vulnerability Traces

### 1.1 Singleton CognitiveLoop State Collision (Showstopper Concurrency Bug)
- **File**: [server.py](file:///e:/AGI/silex/api/server.py#L69-L70) and [cognitive_loop.py](file:///e:/AGI/silex/core/cognitive_loop.py#L627-L630)
- **Mechanism**:
  - The API server initializes and runs a shared singleton instance of `CognitiveLoop` (`shared_loop`).
  - When concurrent chat requests hit `/api/chat/stream`, they execute `shared_loop.process()` concurrently.
  - Inside `process()`, instance variables are re-assigned:
    ```python
    self._turn_start_time = _time_module.time()
    self._pending_tool_audit = []
    ```
- **Vulnerability Trace**:
  - If User A and User B send messages at the same time, User B's thread will overwrite `self._pending_tool_audit` on the shared singleton while User A's thread is executing tools.
  - User A's tool execution logs are appended to the new list created by User B.
  - When User A's request finishes, it flushes `self._pending_tool_audit` inside its own database transaction, persisting User B's tool execution logs as if they belonged to User A.
  - When User B's request finishes, its tool execution logs are either missing or duplicated.
  - This results in a massive security and data integrity leak where audit logs, epistemic nodes, and transaction records cross session boundaries and bleed into other users' request histories.

---

## 2. AI Bloat Detection

### 2.1 Web Onboarding & Catalog Duplication
- **File**: [server.py](file:///e:/AGI/silex/api/server.py#L295-L338)
- **Bloat Description**:
  - The API server mounts endpoints for searching, installing, and uninstalling skills from a remote catalog.
  - These catalog operations are redundant with the Python CLI commands, duplicating the registry update, package validation, and installation logic.
  - They also bypass normal CLI permission structures, allowing any HTTP client with gateway access to write new skill files to `~/.kinthic/skills/`.

---

## 3. Race Conditions & Resilience

### 3.1 StreamingResponse Client Disconnect Leak
- **File**: [server.py](file:///e:/AGI/silex/api/server.py#L236-L266)
- **Mechanism**:
  - The `/api/chat/stream` endpoint uses a `StreamingResponse` wrapping a `generator()` function.
  - Inside `generator()`, the actual reasoning task is spawned in the background:
    ```python
    task = asyncio.create_task(shared_loop.process(req.message, event_emitter=event_emitter, images=req.images))
    ```
- **Failure Trace**:
  - If a user disconnects or closes the HTTP stream mid-turn, Uvicorn cancels the streaming generator task.
  - However, because there is no `try...finally` block to intercept cancellation and call `task.cancel()`, the background task `shared_loop.process()` continues running in the asyncio loop.
  - The cognitive loop will continue to execute heavy tool actions, run terminal commands, and call LLM APIs, completely unaware that the client has disconnected.
  - This is a severe resource exhaustion vector.

### 3.2 Active Cancels Map Memory Leak
- **File**: [server.py](file:///e:/AGI/silex/api/server.py#L205-L208)
- **Mechanism**:
  - A unique `request_id` is generated for every chat stream connection, and a cancel event is added to the global map:
    ```python
    active_cancels[request_id] = cancel_event
    ```
- **Failure Trace**:
  - The `active_cancels` dictionary is never cleared when a request finishes naturally or fails.
  - Over time, the size of this dictionary grows linearly with the number of HTTP requests, leaking memory and eventually crashing the daemon.
