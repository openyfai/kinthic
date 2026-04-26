# ARIA Phase 7: Recursive Self-Improvement Implementation Plan

This document outlines the architecture for Phase 7, the final phase of ARIA's development. This phase tackles the alignment and self-improvement problem. ARIA will monitor her own weaknesses and propose structural changes to her own logic, prompts, and architecture. Crucially, these changes are gated by a hard safety lock (human approval) and validated by a benchmark suite.

## 1. Core Concept: Meta-Reasoning and The Safety Lock

We will introduce a new module `aria/core/meta_reasoning.py` containing the `MetaReasoningEngine`.
Unlike the Cognitive Loop which processes user input, the MetaReasoningEngine processes ARIA's *own performance data* (Critique logs, Debate uncertainties, Tool failures).

**The Safety Lock**: ARIA can *propose* changes, but she cannot *apply* them. Proposals are stored in a database and must be manually approved and implemented by the developer. This is a non-negotiable architectural constraint.

## 2. Schema Evolution (`aria/models/schemas.py`)

New data models for proposals and benchmarks.

```python
class SelfImprovementProposal(BaseModel):
    """A formal proposal from ARIA to modify her own architecture or prompt."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target_system: Literal["system_prompt", "tool_registry", "cognitive_loop", "memory_store", "other"]
    description: str = Field(description="Exactly what should be changed")
    rationale: str = Field(description="Why this change will improve performance based on past failures")
    success_metric: str = Field(description="How to quantitatively measure if this change worked")
    status: Literal["pending", "approved", "rejected", "implemented"] = Field(default="pending")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class BenchmarkResult(BaseModel):
    """A record of ARIA's performance on a fixed evaluation suite."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    score: float = Field(description="Overall benchmark score (0.0 - 100.0)")
    domains_tested: list[str] = Field(description="Which knowledge domains were evaluated")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
```

*Note: `CognitiveResponse` will be updated to include `improvement_proposals: list[SelfImprovementProposal]`.*

## 3. Database Updates (`aria/storage/database.py`)

We need tables to persist proposals and track capability growth over time.

```sql
CREATE TABLE IF NOT EXISTS improvement_proposals (
    id TEXT PRIMARY KEY,
    target_system TEXT NOT NULL,
    description TEXT NOT NULL,
    rationale TEXT NOT NULL,
    success_metric TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_history (
    id TEXT PRIMARY KEY,
    score REAL NOT NULL,
    domains_tested_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

## 4. The Benchmark Suite (`aria/core/benchmark.py`)

To know if a proposed change actually *improves* ARIA, we need a baseline. We will build a simple benchmark runner that throws a fixed set of highly complex, cross-domain problems at ARIA and uses an LLM judge to score her accuracy, depth, and honesty. 

## 5. Cognitive Loop Integration (`aria/core/cognitive_loop.py`)

The `process()` method will add logic to extract and persist `cognitive.improvement_proposals` to the database, flagging them as `pending`.

## 6. Dependencies & UI

- **Terminal UI**: When ARIA generates a proposal, the UI will sound a conceptual "alarm" (rendering a distinct red/magenta alert box) showing the proposal to the user.
- **Commands**: 
  - `:proposals` to list pending self-improvement proposals.
  - `:benchmark` to trigger a run of the Benchmark Suite.

---

### Implementation Steps
1. Add `improvement_proposals` and `benchmark_history` tables to SQLite schema.
2. Add `SelfImprovementProposal` and `BenchmarkResult` schemas; update `CognitiveResponse`.
3. Build `aria/core/meta_reasoning.py` and `aria/core/benchmark.py`.
4. Integrate the extraction of proposals into the `CognitiveLoop`.
5. Update Terminal UI to prominently display proposals and add new CLI commands.
