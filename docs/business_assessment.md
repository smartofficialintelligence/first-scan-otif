# Business assessment — long-delivery model

**Model:** `local-20260816T082828Z`  
**Target:** `long_delivery` = delivery takes **> 14 days** from approval  
**Machine-readable:** `artifacts/business_assessment.json` (gitignored; regenerate via script below)

## Ranking quality (test)

| Metric | Value |
|---|---:|
| PR-AUC | 0.531 |
| ROC-AUC | 0.796 |

## Base rate

| Split | n | Positives | Base rate |
|---|---:|---:|---:|
| Train | 57,887 | 19,729 | **34.1%** |
| Valid | 14,471 | 4,779 | **33.0%** |
| Test | 14,471 | 2,956 | **20.4%** |
| All labeled | 96,476 | 28,261 | **29.3%** |

Test base rate is lower than train/valid (temporal regime shift). Compare precision to the **test** base rate.

## Top-risk segment (test, capacity = 10%)

Flag top **1,447 / 14,471** orders by predicted risk.

| Metric | Value |
|---|---:|
| Precision @ 10% | **64.7%** |
| Recall @ 10% | **31.7%** |
| Lift vs test base rate | **3.17×** (64.7% / 20.4%) |
| Random 10% precision (ref) | ~20.8% |
| Mean P(risk) in flagged | 0.67 |
| Mean basket (flagged) | ~$190 (test overall ~$143) |

**Read:** among the highest-risk tenth of orders, about **2 in 3** are actually long deliveries, and that slice captures about **1 in 3** of all long deliveries — with **~3×** enrichment vs intervening at random.

## Value / cost of intervention (simulated)

These use the **example assumptions** from the deferred decision plan. They are **not** measured causal effects.

```text
loss_if_long = $10 + 0.10 × basket_value
```

| Action | Unit cost | Assumed prevent / impact | Mean EV / flagged order | Total EV (top 10%) | Spend |
|---|---:|---|---:|---:|---:|
| EXPEDITE | $8 | 60% prevent | **+$3.86** | ~$5.6k | $11.6k |
| CUSTOMER_NOTIFICATION | $1 | 0% prevent, 20% impact cut | **+$2.95** | ~$4.3k | $1.4k |
| SELLER_ESCALATION | $4 | 35% prevent | **+$2.92** | ~$4.2k | $5.8k |
| MANUAL_REVIEW | $5 | 30% prevent | **+$0.93** | ~$1.3k | $7.2k |
| NO_ACTION | $0 | — | $0 | $0 | $0 |

EV for prevention actions: `P(risk) × prevent × loss − cost`  
EV for notification: `P(risk) × loss × impact_reduction − cost`

Under these assumptions, intervening on the **top 10%** looks **positive-EV** for EXPEDITE / notification / escalation; MANUAL_REVIEW is marginal. **Do not treat $ as proven ROI** until H9/H10 approve assumptions and the decision layer runs policy replay.

## Business read

- Ranking is strong enough for a capacity-constrained ops demo.
- The actionable story is **enrichment at a budgeted flag rate** (precision/lift @ 10%), not overall accuracy.
- Next modeling is optional; next product step is deterministic EV policy (D1–D2) with versioned assumptions.

## Regenerate

```bash
# After train, from repo root — or re-run the assessment snippet that writes
# artifacts/business_assessment.json
uv run python -m olist_ml.training.pipeline --data-dir data/raw --trials 25
```
