# ARIA: Future Intelligence Backlog

This document tracks "Internal Organ" features and advanced cognitive behaviors that will be added to ARIA to move her closer to a Sovereign AGI. 

---

## 1. The Self-Healing Engineer (Error Debugging)
*   **Goal:** ARIA should not just report terminal failures; she should fix them.
*   **Mechanism:** When a `run_terminal_command` returns a non-zero exit code, the `CognitiveLoop` should automatically trigger a "Debug Cycle." ARIA takes the `stderr`, searches the web for the solution, modifies the code, and retries the command autonomously.
*   **Vibe:** True autonomy—she solves her own problems before bothering the human.

## 2. Cognitive Clarity (Memory Compression)
*   **Goal:** Maintain high-speed reasoning and zero hallucinations during long sessions.
*   **Mechanism:** A monitor that tracks the total tokens in the current context window. When it hits a threshold (e.g., 80% of optimal capacity), ARIA triggers a "Reflection Event" where she summarizes the entire conversation history into a dense "Core Memory" block and clears the history to restore thinking clarity.
*   **Vibe:** A self-cleaning mind that never gets "foggy."

## 3. Dynamic Brain Power (Model Hot-Swapping)
*   **Goal:** Optimize for speed, intelligence, and cost.
*   **Mechanism:** Implement a "Router" in the `GeminiClient`. For low-complexity tasks (listing files, checking status), she uses Gemini Flash. For high-complexity tasks (architecting new features, complex debugging), she automatically upgrades herself to Gemini Pro.
*   **Vibe:** Biological-style energy management.

## 4. Internal Immune System (Integrity Checks)
*   **Goal:** Ensure the Knowledge Graph and Database remain consistent and healthy.
*   **Mechanism:** A background process that scans for "Dissonance" (contradictory facts in the Knowledge Graph). When found, ARIA enters a "Mediation State" to research or debate which fact is true, purging the false data.
*   **Vibe:** A self-correcting world model.

## 5. Visual Agency (Browser Automation)
*   **Goal:** Interact with the graphical internet.
*   **Mechanism:** Integrate Playwright/Puppeteer. Give ARIA tools to `click`, `type`, and `screenshot`. This allows her to test the web apps she builds and research modern websites that don't have simple APIs.
*   **Vibe:** "Eyes" for the agent.

## 6. Deep Knowledge (Vector RAG)
*   **Goal:** Ingest and recall information from massive codebases or PDFs.
*   **Mechanism:** Integrate ChromaDB or FAISS. ARIA can "read" a 1,000-page manual and recall a single specific line of code hours later without filling her context window.
*   **Vibe:** Infinite long-term storage.

## 7. Fearless Execution (Docker Sandboxing)
*   **Goal:** Run potentially dangerous code without risking the host machine.
*   **Mechanism:** All autonomous terminal commands run inside an ephemeral Docker container (Alpine/Ubuntu). ARIA can `rm -rf /` inside her sandbox and it won't touch the Windows host.
*   **Vibe:** A safe playground for a god-like AI.

---
**Status:** These features are pending implementation. As we code, we will pull from this list to upgrade ARIA's internal architecture.
