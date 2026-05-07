# ARIA Project Context & Backup

**Date:** May 2026
**Purpose:** This document contains the full architectural context, recent upgrades, and roadmap for ARIA. It is designed to be read by other AI coding assistants (like Cursor, SWE-agent, or Copilot) to instantly understand the state of the codebase.

---

## 1. Core Identity & Architecture
ARIA is a Tier 3 Autonomous Agent simulating a "Sovereign AGI." She is built to be a proactive software engineer, not just a reactive chatbot.

*   **Backend:** FastAPI (Python 3.10+) running a `CognitiveLoop`.
*   **Frontend:** Next.js 14+ (React, Tailwind, `react-force-graph-2d`).
*   **LLM Engine:** Google Gemini (via `aria/llm/gemini.py`).
*   **State & Memory:** Persistent SQLite database tracking Sessions, Goals, flat Memories, and a Causal Knowledge Graph.

## 2. The Cognitive Loop (`aria/core/cognitive_loop.py`)
This is the heartbeat of ARIA. Every interaction flows through these phases:
1.  **Context Builder:** Injects Identity, active Goals, Knowledge Graph neighbors, History, and Session stats into the system prompt.
2.  **Tool Pass:** Gemini decides if it needs to execute tools (Web Search, Read/Write Files, Run Terminal Commands).
3.  **Execution:** Tools execute. If terminal tools are run, the output is fed back.
4.  **Final Response:** Gemini drafts the final reply and emits structured JSON (`CognitiveResponse`) containing `GoalUpdate`s, `CausalObservation`s (for the Graph), and `NewMemory` events.

## 3. Recent Upgrades (Phase A - UI & Persistence Polish)
We recently completed a major stability and UI pass:

*   **Interactive Knowledge Graph:** Rewrote `aria-ui/src/components/GraphView.tsx`. The graph now uses a custom Canvas renderer. Clicking a node opens a smooth sliding side-panel displaying node metadata (ID, Confidence, Group, Connections) and centers the camera on the node.
*   **Session Persistence:** Prevented amnesia on server restarts. 
    *   Backend (`aria/memory/session.py`): Added `resume_or_start()` to load the most recent unclosed session from SQLite on boot.
    *   Frontend (`useAriaSocket.ts`): Modified the WebSocket payload to always send `session_id: activeSessionId`, allowing the backend to hot-swap to the correct context if the user switches chats.
*   **Bulletproof Goal Tracking:** Tuned the Pydantic schemas in `aria/models/schemas.py` and the prompt in `aria/core/context_builder.py`. ARIA is now under a `CRITICAL` directive to emit an `action="complete"` for any goal she achieves via tool execution.

## 4. Autonomous Capabilities (The "Ghost in the Machine")
ARIA possesses deep system-level control, gated by environment variables in `.env`:
*   `ARIA_AUTONOMOUS_EXECUTION=true`: Allows her `run_terminal_command` and `apply_approved_edit` tools to bypass human approval. She can write code and run bash/powershell scripts directly.
*   `ARIA_ENABLE_BACKGROUND_LOOP=true`: Activates the `Chronos` protocol in `scripts/web_server.py`. ARIA will wake up every 15 minutes, check her goals, and proactively execute tools without the user saying anything.

## 5. Next Steps Roadmap (Phase B - AGI-Tier Upgrades)
If you are an AI assistant picking up this project, these are the immediate next tasks to build:

1.  **Browser Automation (The OpenClaw Upgrade):**
    *   *Goal:* Allow ARIA to visually browse the web and test front-end UIs.
    *   *Implementation:* Integrate Playwright into a new `aria/tools/browser.py` tool. Allow her to navigate, click, type, and take screenshots (feeding the images back into Gemini's multimodal context).
2.  **Deep Document Mastery (Vector DB / RAG):**
    *   *Goal:* Prevent context window overflow when ingesting large codebases or PDFs.
    *   *Implementation:* Add ChromaDB or FAISS. Create an `ingest_document` tool to chunk and embed files, and a `semantic_search` tool for retrieval.
3.  **Safe Sandboxing (Docker Execution):**
    *   *Goal:* Prevent ARIA from accidentally deleting system files when writing code autonomously.
    *   *Implementation:* Create a `run_in_sandbox` tool using the Python Docker SDK. She spins up an ephemeral Alpine container, runs her script, reads stdout, and destroys the container.
4.  **Voice & Audio Interfaces:**
    *   *Goal:* Hands-free interaction via Telegram.
    *   *Implementation:* Integrate OpenAI Whisper for STT and ElevenLabs for TTS.

---
**Note to AI Assistant:** Do not break the Pydantic schemas in `aria/models/schemas.py`. Gemini relies on the exact JSON schema generation from these models to structure its cognitive output. Always use `propose_code_edit` carefully when modifying the Cognitive Loop.
