# Feature / model iteration notes

## 2026-08-18 — promise-miss at handoff (ADR 0006)

Hero target is again **promise-miss**, scored at first carrier scan. Handoff clocks (`handling_days`, `remaining_to_promise_days`, `handling_frac_of_promise`, `limit_miss`) are legal at that moment.

**Full Olist** (`local-20260818T041243Z`, 8 Optuna trials, split on `handoff_ts`):

| Split | n | Miss rate | PR-AUC | ROC-AUC |
|---|---:|---:|---:|---:|
| Valid | 14,471 | 12.3% | 0.478 | 0.838 |
| Test | 14,471 | 4.6% | **0.296** | 0.816 |

Persisted policy thresholds from **validation** scores: P1 **0.5625** (top 2.5%), P2 **0.3155** (top 10%). Test @ 2.5% / 10% capacity: precision 41.6% / 22.2% (lifts 9.0× / 4.8× vs 4.6% base). Interviewer tables: [business_assessment.md](business_assessment.md).

Approval-time promise-miss was ~0.10–0.20 PR-AUC. Duration `long_delivery` (below) is the diagnostic / PIT-rate appendix, not the hero.

---

Date: 2026-08-16  
Branch: `cursor/feature-model-iteration-642f`  
Model: `local-20260816T082828Z`

## Problem change (ADR 0005) — superseded as hero

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
