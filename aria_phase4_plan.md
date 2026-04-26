# ARIA Phase 4: Multi-Agent Debate Implementation Plan

This document outlines the architecture for Phase 4. The goal is to solve the problem of self-reinforcing bias by introducing adversarial reasoning. When ARIA encounters a highly complex, uncertain, or controversial topic, she will split into three distinct personas (Agent A, Agent B, and a Judge) to debate the issue before returning a synthesized truth to the user.

## 1. Core Concept: The Debate Engine

We will introduce a new subsystem, the `DebateEngine`, which orchestrates a structured argument.
1. **Priors Injection**: Agent A is prompted to take a strong "Pro" or "Perspective 1" stance. Agent B is prompted to take a strong "Con" or "Perspective 2" stance.
2. **The Exchange**: 
   - Round 1: Agent A opening, Agent B opening.
   - Round 2: Agent A rebuttal, Agent B rebuttal.
3. **The Judgment**: A third instance, the "Judge", reads the transcript. The Judge has not been tainted by the priors. It evaluates the logical strength, identifies fallacies, and produces a final synthesis.
4. **Graph Updating**: The winning arguments (and the newly discovered weaknesses of the losing arguments) are automatically injected into the Causal Knowledge Graph.

## 2. Schema Evolution (`aria/models/schemas.py`)

New data models for structured outputs during the debate.

```python
class DebateArgument(BaseModel):
    agent_id: Literal["Agent A", "Agent B"]
    claim: str
    reasoning: str
    evidence_or_logic: str

class DebateResolution(BaseModel):
    summary: str
    strongest_points_a: list[str]
    strongest_points_b: list[str]
    synthesis: str = Field(description="The final truth derived from the clash")
    graph_updates: list[CausalObservation] = Field(description="New causal links discovered")

class UncertaintyTopic(BaseModel):
    """The Disagreement Tracker."""
    id: str
    topic: str
    why_uncertain: str
    status: Literal["open", "resolved"]
```

## 3. Database Updates (`aria/storage/database.py`)

We need tables to persist the outcomes of debates and track known uncertainties.

```sql
CREATE TABLE IF NOT EXISTS debates (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    transcript_json TEXT NOT NULL,
    resolution_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS uncertainties (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    why_uncertain TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
```

## 4. New Module: `aria/core/debate.py`

This engine will manage the prompts and API calls for the three personas.

```python
class DebateEngine:
    def __init__(self, gemini_client, db, knowledge_graph):
        self.gemini = gemini_client
        ...

    async def run_debate(self, topic: str, rounds: int = 2) -> DebateResolution:
        # 1. Initialize prompts for A and B
        # 2. Loop through rounds, generating DebateArguments
        # 3. Pass transcript to Judge
        # 4. Save to DB
        # 5. Return DebateResolution
        ...
```

## 5. Cognitive Loop Integration (`aria/core/cognitive_loop.py`)

ARIA will need a way to *choose* to debate. If the `user_input` is highly complex, or if the user explicitly types `:debate <topic>`, the `CognitiveLoop` will hand execution over to the `DebateEngine`.

```python
# Pseudo-code addition to process()
if is_highly_complex(user_input) or user_requested_debate:
    resolution = await self.debate_engine.run_debate(user_input)
    await self._apply_graph_updates(resolution.graph_updates)
    return CognitiveResponse(response=resolution.synthesis, ...)
```

## 6. Terminal UI Updates (`aria/ui/terminal.py`)

The terminal needs a dramatic way to show a debate in progress.
- Using `rich.layout` or alternating colored panels (e.g., Red for Agent A, Blue for Agent B) streaming in real-time or stepping through.
- New commands: 
  - `:debate <topic>` (force a debate)
  - `:debates` (list past debates)
  - `:uncertainties` (view the disagreement tracker)

---

### Implementation Steps
1. **Schemas & DB**: Add `DebateArgument`, `DebateResolution`, `UncertaintyTopic` and SQLite tables.
2. **Debate Engine**: Build `aria/core/debate.py` with the 3 distinct system prompts (A, B, Judge).
3. **UI Display**: Build `show_debate_progress` in `terminal.py` for an engaging visual experience.
4. **Wiring**: Connect it to the main `run.py` and `cognitive_loop.py` so the user can trigger it manually.
