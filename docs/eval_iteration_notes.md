# Feature / model iteration notes

Date: 2026-08-16  
Branch: `cursor/feature-model-iteration-642f`  
Model: `local-20260816T082828Z`

## Problem change (ADR 0005)

Original promise-miss target was too weak for a prod demo (~8% positive; test PR-AUC ~0.10–0.20).

**New target:** `long_delivery = delivery_days > 14` from `prediction_ts` (~29% overall).

## Full Olist metrics (temporal split)

| Split | PR-AUC | ROC-AUC | Brier | ECE |
|---|---:|---:|---:|---:|
| Valid | 0.728 | 0.850 | 0.145 | ~0.000 |
| Test | **0.531** | 0.796 | 0.129 | 0.031 |

Test @ 10% capacity: see `artifacts/eval_report.json` (precision typically ~0.55–0.60 in smoke runs).

## Prior promise-miss baseline (for comparison)

- Test PR-AUC ≈ 0.096 → 0.197 after feature iteration (still not demo-grade)

## Follow-up (2026-08-18): duration − promise

See [experiments/overrun_duration.md](experiments/overrun_duration.md).

Duration regression minus promised horizon **does not** recover a demo-grade miss ranker (test PR-AUC ~0.20 on `promise_miss`, prec@10% ~17%). It slightly beats a binary miss classifier. Mean delivery is **14.5 days earlier** than the estimate — ETAs are padded, residual is weak at capacity.

Reproduce:

```bash
uv run python -m olist_ml.training.pipeline --data-dir data/raw --trials 25
```
