# Experiment: duration regression − promise (overrun ranker)

Date: 2026-08-18  
Script: `scripts/experiment_overrun_ranker.py`  
Data: full Olist, same temporal split as production (`n_test=14,471`)

## Why

`long_delivery = delivery_days > 14` is learnable (test PR-AUC ~0.53) but is **not** “customer was failed.”  
This run checks whether `predicted_duration − promised_horizon` can rank **promise misses** well enough to tell a coherent ops story without a platform refactor.

## What we trained (existing PIT features)

| Scorer | How the score is built |
|---|---|
| `duration_minus_promise` | XGB regress `delivery_days`, score = pred − `estimated_horizon` |
| `duration_minus_promise_no_horizon_in_X` | Same, horizon **dropped from X** |
| `days_late_regression` | XGB regress `delivered − estimated` |
| `promise_miss_binary` | XGB classify `delivered > estimated` |
| `long_delivery_binary` | Current production-style `>14d` classifier (cross-eval on miss) |

## Test facts (important)

| | |
|---|---:|
| Promise-miss rate | **4.8%** |
| Long-delivery (>14d) rate | **20.4%** |
| Mean days late (delivered − estimate) | **−14.5 days** (typically *early*) |
| Mean promised horizon | **24.2 days** |
| Mean predicted duration | **11.7 days** |
| Corr(pred duration, promise) | **0.73** |

Olist ETAs are **padded**. The duration model says ~12 days; the promise says ~24.

Duration fit: MAE ~4.6d, R² ~0.24. Days-late regression: MAE ~4.8d, R² ~0.56 (residual is large because of that buffer).

## Ranking promise-miss (the salvage metric)

| Scorer | PR-AUC | ROC-AUC | Prec@10% | Lift vs 4.8% |
|---|---:|---:|---:|---:|
| duration − promise (no h in X) | **0.202** | 0.787 | **17.3%** | 3.60× |
| days_late regression | 0.199 | 0.779 | 15.7% | 3.27× |
| duration − promise | 0.194 | 0.781 | 16.1% | 3.36× |
| promise_miss binary | 0.162 | 0.751 | 15.8% | 3.30× |
| long_delivery binary | 0.061 | 0.555 | 7.7% | 1.60× |

For comparison, production **long_delivery** on its *own* label: PR-AUC **0.529**, prec@10% **64.6%**, lift 3.16×.

## How to read this

- Duration-then-subtract **≈ days-late regression**, as the math said. Tiny edge to “no horizon in X.”
- Both **beat binary miss** a bit (0.20 vs 0.16 PR-AUC). Training trick helped; it did **not** create a new physical signal.
- ROC ~0.78 on miss is real discrimination. PR-AUC ~0.20 and prec@10% ~17% are the ops numbers: at a 10% flag rate you still mostly flag on-time orders, because misses are rare.
- Production `long_delivery` is **bad** at ranking actual promise-miss (PR-AUC 0.06). Slow ≠ late. That is the business objection, measured.

## Decision

Do **not** replace the champion target with overrun/miss for the portfolio ranker. The conceptually right label stays weak at capacity.

Viable honest story:

1. Keep duration / `>14d` as a **slow-path ranker** (strong metrics; not “failed SLA”).
2. Optionally expose overrun `pred_days − promise` as a **secondary diagnostic** (ROC ~0.78 on miss; do not claim 65% precision).
3. If the interview needs “missed promise,” show these numbers and the padded-ETA fact (mean 14.5 days early).

Reproduce:

```bash
uv run python scripts/experiment_overrun_ranker.py
# → artifacts/overrun_experiment.json
```
