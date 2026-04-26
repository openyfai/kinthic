# ARIA Phase 6: Transfer + Generalization Implementation Plan

This document outlines the architecture for Phase 6. The goal is to move ARIA from a "smart database of facts" to a system capable of true general intelligence by implementing cross-domain knowledge transfer. When ARIA learns a specific fact in one domain, she will extract the underlying structural pattern so it can be applied to completely unrelated domains.

## 1. Core Concept: The Generalization Engine

We will introduce a new module `aria/core/generalization.py` that contains the `GeneralizationEngine`. 
This engine has two distinct responsibilities:
1. **Upward Abstraction**: When Phase 2's World Model identifies a new causal link (e.g., "High interest rates cause tech stocks to drop"), the Generalization Engine abstracts it into a universal law (e.g., "The Cost of Capital Principle: When the baseline cost of resources increases, speculative investments collapse first").
2. **Downward Application (Analogies)**: When answering a user's question, ARIA must attempt to use these universal principles to generate structural analogies.

## 2. Schema Evolution (`aria/models/schemas.py`)

New data models for abstract principles and analogies.

```python
class UniversalPrinciple(BaseModel):
    """A cross-domain structural law extracted from specific facts."""
    id: str
    name: str = Field(description="A memorable name for the principle (e.g. 'The Friction Law')")
    statement: str = Field(description="The abstract, domain-agnostic rule")
    original_domain: str = Field(description="The specific domain where this was learned")
    applicable_domains: list[str] = Field(description="Other domains where this likely applies")
    created_at: str

class Analogy(BaseModel):
    """A structural mapping between two different domains."""
    source_domain: str = Field(description="The domain the user is asking about")
    target_domain: str = Field(description="A completely different domain used for comparison")
    mapping: str = Field(description="How the underlying structures exactly match")
```

*Note: `CognitiveResponse` will be updated to include `analogies: list[Analogy]`.*

## 3. Database Updates (`aria/storage/database.py`)

We need a table to persist these abstract principles.

```sql
CREATE TABLE IF NOT EXISTS principles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    statement TEXT NOT NULL,
    original_domain TEXT NOT NULL,
    applicable_domains_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

## 4. Context Injection (`aria/core/context_builder.py`)

The system prompt must be updated so ARIA is constantly aware of her own generalized principles.
We will add a new section to the system prompt:
```text
═══════════════════════════════════════════════════════════
UNIVERSAL PRINCIPLES
═══════════════════════════════════════════════════════════
You have discovered the following abstract laws. Use them to draw 
structural analogies across different domains when explaining complex topics:
- [The Friction Law]: Any structural barrier reduces flow...
```

## 5. Cognitive Loop Integration (`aria/core/cognitive_loop.py`)

The `process()` method will add a generalization step at the very end (background processing):

```python
# Step 9: Build knowledge graph from causal observations
graph_updates = await self._process_causal_observations(cognitive.causal_observations)

# Step 9.5: Abstract new principles (Phase 6)
if graph_updates > 0:
    await self.generalization_engine.abstract_principles(cognitive.causal_observations)
```

## 6. Dependencies & UI

- **Terminal UI**: We will update the terminal to beautifully render the `Analogy` blocks in yellow/cyan when ARIA outputs them, highlighting her cross-domain reasoning.
- **Commands**: Add `:principles` to see the list of abstracted laws she has learned over time.

---

### Implementation Steps
1. Add `principles` table to SQLite schema.
2. Add `UniversalPrinciple` and `Analogy` schemas; update `CognitiveResponse`.
3. Build `aria/core/generalization.py` to handle the abstraction logic via Gemini.
4. Integrate `ContextBuilder` and `CognitiveLoop` with the new engine.
5. Update Terminal UI to display analogies and the `:principles` command.
