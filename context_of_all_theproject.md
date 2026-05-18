# The Complete Context & Vision of VYN (formerly ARIA)

*This document serves as the absolute master reference for the project. It captures the foundational philosophy, the cognitive architecture, the overarching vision, and the historical context of the transition from ARIA to VYN.*

---

## Part 1: The Origin and The Vision (Why We Are Building This)

### The Pursuit of AGI
We are building **VYN** because modern AI systems are fundamentally flawed: they are stateless, forgetful, and exist only in isolated chat windows. We are building toward **Artificial General Intelligence (AGI)** by creating an AI that is *alive, autonomous, and continuous*.

We wanted an AI operator that:
1. **Lives Locally**: Resides on your machine, completely private and sovereign.
2. **Has Infinite Memory**: Never forgets a conversation, a coding pattern, or a preference. It builds a complex "World Model" over time.
3. **Has True Agency**: Can browse the web, write code, execute terminal commands in a sandbox, and perform tasks entirely in the background.
4. **Learns and Reflects**: Doesn't just blindly answer questions, but criticizes its own thoughts, tracks contradictions, and updates its understanding of the world.

### ARIA vs. VYN
*   **ARIA (The Engine)**: Originally the name of the entire project, ARIA stands for the cognitive architecture—the memory store, the vector database, the knowledge graph, and the semantic reasoning engine.
*   **VYN (The Identity)**: VYN is the persona and the overarching agent that interacts with the user. VYN *uses* the ARIA engine to think and remember.

---

## Part 2: How It Works (The Cognitive Architecture)

VYN is not a simple script; it is a complex, continuous daemon (background process) that runs a **Cognitive Loop**.

### 1. The Cognitive Loop
Every time you speak to VYN, it doesn't just pass text to an LLM. It:
*   **Retrieves Context**: Pulls relevant memories from ChromaDB (Vector Store) and SQLite.
*   **Thinks**: Forms a hypothesis, notes contradictions, and plans tool usage.
*   **Critiques Itself**: An internal critic model reviews the plan before executing it to ensure safety and accuracy.
*   **Acts**: Uses tools (like Web Search, Browser Manipulation, Terminal Execution, Code Editing).
*   **Reflects & Stores**: After acting, it extracts new facts and stores them permanently as Normative (rules), Character (identity), or Semantic (facts) memories.

### 2. The Memory Engine
VYN uses a dual-memory system:
*   **Structured Storage (SQLite)**: Stores memories with strict provenance (who said it, when, what was the confidence level).
*   **Semantic Storage (ChromaDB)**: A vector database that allows VYN to instantly recall vaguely related concepts across tens of thousands of past interactions.

### 3. The Phantom Sandbox
To give VYN the ability to write and run code without destroying your local machine, we built the **Phantom Sandbox**. This is an isolated Docker container where VYN can safely run Python, shell scripts, and complex tools.

### 4. The Ontology (World Model)
VYN actively maps relationships in a Knowledge Graph (e.g., "User" -> "prefers" -> "Python"). When it encounters conflicting information, it flags a "contradiction" and asks you for clarification, actively repairing its worldview.

---

## Part 3: VYN Migration & Recent Hardening Summary

*The following details the recent transition from the legacy ARIA structure to the modern VYN infrastructure.*

## 1. Identity & Branding Transition
The project has been fully transitioned from its legacy identity (**ARIA**) to its new identity (**VYN**). 
*   **System Identity:** VYN is the AI operator/agent, powered internally by the ARIA memory engine.
*   **Package Name:** `openyfai-vyn` (bumped to version `1.2.0`).
*   **CLI Entry Points:** `vyn web`, `vyn setup`, `vyn start`, `vyn stop`, `vyn models`, `vyn doctor`.
*   **Documentation:** `README.md`, `docs/quickstart.md`, `CONTRIBUTING.md`, and `skills/README.md` have been fully rewritten to reflect the new commands, installation paths, and architectural vision.
## 2. Infrastructure & Path Migration
A massive decoupling was executed to move all runtime data, configuration, and state out of the project root and into a professional, centralized home directory: **`~/.vyn`** (`Path.home() / ".vyn"`).
The new directory structure managed by `aria.utils.config` and `aria.runtime.settings`:
*   **`~/.vyn/vyn.db`**: Primary SQLite database for memory, graph, and cognitive state.
*   **`~/.vyn/settings.json` / `secrets.json`**: System configuration and API keys.
*   **`~/.vyn/workspace/`**: The sandboxed directory where VYN reads/writes files and executes commands.
*   **`~/.vyn/memory/vector_db/`**: ChromaDB persistent storage for semantic search and infinite recall.
*   **`~/.vyn/skills/`**: Markdown-based dynamic skill loading.
*   **`~/.vyn/logs/` & `daemon.lock`**: Background daemon state and logs.
*   **`~/.vyn/.phantom/`**: Sandboxed environment for the Phantom Sandbox.
*Note: Critical legacy environment variables (like `ARIA_WORKSPACE`) were retained as aliases for backwards compatibility, but default to the new `VYN_` structure.*
## 3. Security & Reliability Hardening
Extensive security and robustness upgrades were implemented and verified against the test suite (100% pass rate: 51/51 tests):
*   **CLI Daemon Stop (`vyn stop`)**: Refactored to completely close shell injection vulnerabilities. Corrupted or malicious PID files (e.g., containing `rm -rf /`) are now caught gracefully via type coercion (`ValueError`), rather than being passed to underlying OS functions. Stale PIDs are accurately detected via `os.kill(pid, 0)` and cleaned up without crashing.
*   **Docker Asynchronous Execution**: Fixed a critical blocking issue in `aria.tools.system` where `container.wait` and `container.logs` would freeze the primary event loop. These operations are now correctly offloaded to a thread pool via `asyncio.to_thread`.
*   **Test Suite Isolation**: Modified unit tests (e.g., in `test_cognitive_loop.py`) to patch `aria.memory.vector_store.DATA_DIR` to use temporary directories (`tmp_path`). This guarantees that running `pytest` does not accidentally pollute or overwrite your real `~/.vyn/vector_db` data, resolving intermittent duplicate-detection test failures.
## 4. Outstanding Technical Debt (Phase B)
While the system is highly stable, the following technical debt items were deferred and should be addressed in future phases:
1.  **SQL Traversal Replacement (Performance)**:
    *   *Current State*: Graph traversal operations in the worker read-path currently rely on the `networkx` library.
    *   *Action*: Replace `networkx` with SQLite recursive Common Table Expressions (CTEs) for highly optimized, native graph traversal directly within the database engine.
2.  **Heartbeat Telegram Alerts (Reliability)**:
    *   *Current State*: The daemon watchdog can detect and kill a frozen worker process.
    *   *Action*: Implement an active `[ALERT]` notification system to send a Telegram message to the paired user whenever the watchdog intervenes to restart a stalled cognitive loop.
## 5. Next Steps for Release
Once you have renamed your root project folder (e.g., `E:\AGI` -> `E:\VYN`), you are ready to publish:
1.  **Rebuild UI Assets**: Run `npm install` and `npm run build` inside `aria-ui/` to ensure the latest Next.js dashboard is compiled.
2.  **Build Python Wheel**: Run `python -m build` in the project root.
3.  **Publish to PyPI**: Upload the `dist/` artifacts to PyPI under the new `openyfai-vyn` package name (or push the `v1.2.0` tag to trigger your GitHub Actions Trusted Publisher workflow).
---
*Generated: May 18, 2026*
*Status: Ready for Deployment (v1.2.0)*
