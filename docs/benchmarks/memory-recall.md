# Memory Recall Benchmark

Reproducible **needle-in-haystack** evaluation for the Silex memory engine. Proves that hybrid retrieval (keyword + semantic RRF) finds specific facts buried among hundreds of distractor memories — including facts stored weeks ago.

This is **not** the `:benchmark` LLM reasoning suite (`silex/core/benchmark.py`). That measures answer quality on physics/philosophy questions. This benchmark measures **retrieval accuracy**.

## What it tests

- **12 needle facts** with paraphrased queries (not copy-paste of stored text)
- **500 distractor memories** (configurable) simulating conversation noise
- **Three conditions**: fresh, aged 21 days, aged 21 days at low importance
- **Four baselines**: no memory, keyword-only (FTS), vector-only (Chroma), Kinthic hybrid (RRF)

## Metrics

| Metric | Meaning |
|--------|---------|
| Hit@5 / Hit@12 | Fraction of queries where the correct needle appears in top-k results |
| MRR | Mean reciprocal rank of the first correct hit |
| p50 / p95 ms | Retrieval latency per query |
| FP@1 | Top result partially matches but is not the correct needle |

## Quick run

```bash
# Full publish suite (500 noise, all conditions, ~1 min)
kinthic benchmark recall --seed 42

# Fast CI-style run
kinthic benchmark recall --seed 42 --noise 50 --conditions aged_21d

# Equivalent
python -m benchmarks.memory_recall.harness --seed 42
python scripts/mcp_recall_benchmark.py --seed 42 --noise 50
```

Requires `chromadb` (`pip install kinthic[vector]` or `uv sync --extra vector`).

## Published results (v1)

Environment: Python 3.11+, ChromaDB, seed **42**, **500** noise memories, suite v1.

### Condition: `aged_21d` (3-week-old needles)

| Baseline | Hit@5 | Hit@12 | MRR |
|----------|------:|-------:|----:|
| No memory | 0% | 0% | 0.000 |
| Keyword only | 42% | 50% | 0.278 |
| Vector only | 92% | 92% | 0.875 |
| **Kinthic hybrid** | **67%** | **92%** | **0.330** |

Full JSON: [`benchmarks/memory_recall/results/kinthic-v1.json`](../../benchmarks/memory_recall/results/kinthic-v1.json)

Human report: [`benchmarks/memory_recall/results/REPORT.md`](../../benchmarks/memory_recall/results/REPORT.md)

### How to read this

- **No memory** is the raw-LLM baseline — zero retrieval by design.
- **Keyword only** struggles on paraphrased queries (e.g. "What's my dog's name?" vs stored "Pixel").
- **Vector only** is strong on semantic similarity but misses some lexical matches.
- **Hybrid RRF** combines both pools; Hit@12 matches vector while improving over keyword-only on paraphrase-heavy queries.

## Suite definition

Needles and noise templates live in [`benchmarks/memory_recall/suite.yaml`](../../benchmarks/memory_recall/suite.yaml).

## CI regression

`tests/test_memory_recall_benchmark.py` runs a fast gate (50 noise, seed 42) asserting hybrid ≥ keyword on Hit@5/Hit@12 and Hit@12 ≥ 85%.

## End-to-end demo (asciinema)

For a human-visible session recording:

```bash
bash demos/memory_recall_demo.sh
# or: asciinema rec demos/memory_recall_demo.sh
```

This stores a fact via MCP, injects noise, and recalls it with a natural-language query — the same flow users feel in production.
