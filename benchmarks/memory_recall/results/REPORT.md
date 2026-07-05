# Memory Recall Benchmark Report

- Suite version: 1
- Seed: 42
- Noise memories: 500
- Generated: 2026-07-05T17:35:27.076388+00:00
- Vector store active: True

## Condition: `fresh`

| Baseline | Hit@5 | Hit@12 | MRR | p50 ms | p95 ms | FP@1 |
|---|---:|---:|---:|---:|---:|---:|
| none | 0.00% | 0.00% | 0.000 | 0.0 | 0.0 | 0.00% |
| keyword | 41.67% | 66.67% | 0.282 | 1.4 | 1.7 | 8.33% |
| vector | 91.67% | 91.67% | 0.875 | 145.6 | 148.0 | 8.33% |
| hybrid | 83.33% | 91.67% | 0.497 | 148.8 | 152.7 | 8.33% |

## Condition: `aged_21d`

| Baseline | Hit@5 | Hit@12 | MRR | p50 ms | p95 ms | FP@1 |
|---|---:|---:|---:|---:|---:|---:|
| none | 0.00% | 0.00% | 0.000 | 0.0 | 0.0 | 0.00% |
| keyword | 41.67% | 50.00% | 0.278 | 1.5 | 1.6 | 8.33% |
| vector | 91.67% | 91.67% | 0.875 | 146.6 | 147.8 | 8.33% |
| hybrid | 66.67% | 91.67% | 0.330 | 148.9 | 149.3 | 8.33% |

## Condition: `aged_21d_low_importance`

| Baseline | Hit@5 | Hit@12 | MRR | p50 ms | p95 ms | FP@1 |
|---|---:|---:|---:|---:|---:|---:|
| none | 0.00% | 0.00% | 0.000 | 0.0 | 0.0 | 0.00% |
| keyword | 16.67% | 16.67% | 0.167 | 1.4 | 1.7 | 0.00% |
| vector | 91.67% | 91.67% | 0.875 | 144.1 | 146.4 | 8.33% |
| hybrid | 16.67% | 50.00% | 0.062 | 144.9 | 146.9 | 0.00% |

## Reproduce

```bash
kinthic benchmark recall --seed 42 --noise 500
```
