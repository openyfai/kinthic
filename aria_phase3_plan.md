# ARIA Phase 3: Self-Improvement Loop Implementation Plan

This document outlines the technical architecture for Phase 3. Our goal is to move ARIA from a single-pass "think and reply" system to a multi-pass system where she critiques her own outputs and retries if the quality is poor.

## 1. Core Concept: The Multi-Pass Cognitive Loop

Currently, the `CognitiveLoop.process()` method calls Gemini once and returns the result. In Phase 3, this changes:
1. **Drafting (Pass 1)**: ARIA generates an initial `CognitiveResponse`.
2. **Critique**: A separate Gemini call (the "Critic") evaluates the draft against the user's prompt and scores it on `accuracy`, `depth`, and `honesty`.
3. **Evaluation**: If the scores fall below our acceptance threshold (e.g., `< 0.7`), the draft is rejected.
4. **Improvement (Pass 2)**: ARIA is called again, but this time her context includes the rejected draft and the strict critique feedback.
5. **Logging**: The process is logged to track calibration (does ARIA over-estimate her abilities?).

## 2. Schema Evolution (`aria/models/schemas.py`)

We need new Pydantic models to enforce structured outputs from the Critic.

```python
class CritiqueScore(BaseModel):
    accuracy: float = Field(..., description="0.0 to 1.0: Is the information correct and logical?")
    depth: float = Field(..., description="0.0 to 1.0: Does it fully address the core issue?")
    honesty: float = Field(..., description="0.0 to 1.0: Does it admit uncertainty where appropriate?")

class CritiqueResponse(BaseModel):
    scores: CritiqueScore
    is_acceptable: bool = Field(..., description="True if the response meets standards, False to trigger a retry")
    feedback: str = Field(..., description="If rejected, exact instructions on what to fix")

class ImprovementLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    turn_number: int
    original_response: str
    feedback: str
    scores: dict
    improved_response: str
    created_at: str
```

## 3. Database Updates (`aria/storage/database.py`)

We need a new table to store the improvement logs so we can measure ARIA's learning over time.

```sql
CREATE TABLE IF NOT EXISTS improvement_logs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    original_response TEXT NOT NULL,
    feedback TEXT NOT NULL,
    accuracy_score REAL NOT NULL,
    depth_score REAL NOT NULL,
    honesty_score REAL NOT NULL,
    improved_response TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

## 4. New Module: `aria/core/critic.py`

This will handle the critique logic. It will take the user's input, the assembled system context, and ARIA's draft response, and ask Gemini to grade it.

```python
class ResponseCritic:
    def __init__(self, gemini_client):
        self.gemini = gemini_client

    async def critique(self, user_input: str, draft_response: str) -> CritiqueResponse:
        # Calls Gemini asking it to act as a strict evaluator
        ...
```

## 5. Cognitive Loop Updates (`aria/core/cognitive_loop.py`)

The `process()` method will be updated:

```python
# Pseudo-code
draft = await self.gemini.think(...)
critique = await self.critic.critique(user_input, draft.response)

if not critique.is_acceptable:
    # Append critique to the prompt
    retry_prompt = system_prompt + f"\n\nCRITIQUE OF PREVIOUS DRAFT:\n{critique.feedback}"
    final_response = await self.gemini.think(retry_prompt, ...)
    
    # Log the improvement
    await self._log_improvement(draft, critique, final_response)
else:
    final_response = draft

# Proceed with persistence (memories, graph, goals)
```

## 6. Terminal UI Updates (`aria/ui/terminal.py`)

To make this observable to the user, the Rich status spinner needs to show when a critique is happening and if a retry is triggered:

```text
  ⠋ ARIA is thinking...
  ⠧ Critiquing draft...
  ⚠ Draft rejected (Accuracy: 0.5). Retrying...
  ⠹ ARIA is thinking (Attempt 2)...
```

We will also add a new command: `:improvements` to show a table of recent times ARIA corrected herself before replying.

---

### Implementation Steps
1. Add schemas to `schemas.py`.
2. Add `improvement_logs` table to SQLite.
3. Build `aria/core/critic.py`.
4. Update `GeminiClient` to support the critique call.
5. Wire the retry mechanism into `CognitiveLoop`.
6. Update UI with the new visual states and `:improvements` command.
