# ARIA Phase B: The AGI-Tier Expansion Plan

This plan outlines the next 3 major milestones to transition ARIA from a "Chatbot with Tools" to an "Autonomous Digital Entity."

---

## Milestone 1: Visual Agency (Browser Automation)
**Goal:** Give ARIA the ability to browse the web, test UIs, and research real-time data.

1.  **Setup Playwright:** Install `playwright` and `playwright-stealth` in the Python backend.
2.  **Create `browser.py` Tool:** 
    *   `navigate_to(url)`: Opens a headless Chromium instance.
    *   `scrape_page()`: Returns clean Markdown of the page text.
    *   `take_screenshot()`: Captures a 1080p image and feeds it into Gemini's multimodal input.
    *   `click_element(selector)` / `type_text(selector, text)`: Basic interactions.
3.  **Visual Feedback Loop:** Update the `CognitiveLoop` so if ARIA builds a website, she can "open" it in her own browser, take a screenshot, and self-correct her CSS/HTML based on what she "sees."

## Milestone 2: Infinite Recall (Vector DB / RAG)
**Goal:** Enable ARIA to master massive codebases and documentation without hitting context limits.

1.  **Integrate ChromaDB:** Add a local vector store to the `data/` directory.
2.  **Automatic Indexing:** Implement a background job that chunks and embeds the entire workspace.
3.  **`semantic_search(query)` Tool:** Allows ARIA to find relevant code snippets across hundreds of files using natural language.
4.  **Long-Term Fact Retrieval:** Move old, less-relevant Knowledge Graph facts into the Vector DB to keep the "Active Graph" fast.

## Milestone 3: Safe Autonomy (Docker Sandboxing)
**Goal:** Allow ARIA to run dangerous shell commands and scripts with zero risk to your Windows host.

1.  **Docker Integration:** Use the `docker` Python SDK.
2.  **Ephemeral Containers:** Create a system where `run_terminal_command` spins up a lightweight Alpine Linux container.
3.  **Volume Mapping:** Map a specific `sandbox/` folder to the container so she can write and run code in isolation.
4.  **Autonomous Gating:** Once sandboxing is live, we can turn on `ARIA_AUTONOMOUS_EXECUTION=true` with 100% confidence.

---

## Bonus: The "Internal Organs" Pass
Interspersed with the milestones above, we will implement the high-priority items from the `ARIA_FUTURE_BRAIN.md`:
*   **Self-Healing:** Automatically triggering a retry-with-fix when a terminal command fails.
*   **Context Pruning:** Automatic summarization of long chat histories.
*   **Model Routing:** Using Gemini Flash for simple tool calls and Gemini Pro for deep architecture.

---

### Immediate Next Step
We start with **Milestone 1, Step 1: Playwright Integration.**

Ready to install the browser dependencies?
