# Business assessment — promise-miss at carrier handoff

**Hero product:** first-scan NOC queue ([ADR 0006](adr/0006-handoff-promise-miss-noc.md)).  
**Model:** `local-20260818T041243Z` (8 Optuna trials on full public Olist).  
**Target:** `promise_miss` = customer delivery after `order_estimated_delivery_date`.  
**Decision time:** `handoff_ts = order_delivered_carrier_date`. Splits and PIT history use that clock.  
**Machine-readable:** `artifacts/eval_report.json` / `artifacts/model_meta.json` (gitignored).

Exec KPIs for the demo are **$ / customer / dates under versioned simulation assumptions** — not PR-AUC. See [limitations-assumptions-proxies.md](limitations-assumptions-proxies.md). `allow_causal_roi_claims: false`.

## Ranking quality (test, n=14,471)

| Metric | Value | Bootstrap 95% CI |
|---|---:|---|
| PR-AUC | **0.296** | 0.264 – 0.329 |
| ROC-AUC | **0.816** | 0.799 – 0.833 |
| Brier | 0.038 | 0.035 – 0.041 |

Valid (threshold-setting) PR-AUC **0.478** / ROC-AUC **0.838**.

This is **not** the ADR 0005 long-delivery ranker (test PR-AUC ~0.53 on a 20%+ duration label). Promise-miss is rarer and operationally the right OTIF question. Handoff clocks lift it well above the approval-time promise-miss baseline (~0.10–0.20).

## Base rate (temporal shift)

| Split | n | Misses | Base rate |
|---|---:|---:|---:|
| Train | 57,886 | 4,502 | **7.8%** |
| Valid | 14,471 | 1,773 | **12.3%** |
| Test | 14,471 | 669 | **4.6%** |
| Replay | 9,647 | 882 | **9.1%** |
| All labeled | 96,475 | 7,826 | **8.1%** |

Test miss rate is lower than train/valid. Compare precision to the **test** base rate. Persisted policy thresholds come from **validation scores**, so the later test book is a harder, lower-score regime (P1 queue will be smaller than 2.5% of later volume).

## Queue / capacity (test)

Flag by predicted risk. Policy bands use **validation** score cutoffs, not these test-set percentiles.

| Capacity | n flagged | Precision | Recall | Lift vs 4.6% base |
|---:|---:|---:|---:|---:|
| 2.5% (P1-sized) | 361 | **41.6%** | 22.4% | **9.0×** |
| 5% | 723 | 30.7% | 33.2% | 6.6× |
| 7.5% | 1,085 | 25.1% | 40.7% | 5.4× |
| 10% (P2-sized) | 1,447 | **22.2%** | 48.0% | **4.8×** |

**Read:** among the highest-risk fortieth of later orders, about **2 in 5** actually miss the promise (~9× a random draw). The top tenth captures about **half** of test misses at ~5× enrichment.

### Persisted policy thresholds (from validation scores)

| Band | Capacity on valid | Score threshold | Valid precision |
|---|---:|---:|---:|
| P1 | top 2.5% | **0.5625** | 75.9% |
| P2 | top 10% | **0.3155** | 50.7% |

P0 (`remaining ≤ 0` → `LATE_NOTICE`) is a clock rule, not a ranker. P1 upgrade eligibility still requires `0 < remaining ≤ 7` and (`geo ≥ 100km` or not same state).

## Value / cost of intervention (simulated)

These use **econ-sim-v3** placeholders. They are **not** measured causal effects.

```text
miss_cost = $10 + 0.10 × basket_value
upgrade_cost = clip(freight × lognormal(median 0.50×, σ_log 0.35), min $5, max min($80, 8% basket))
```

| Action | When | OTIF recovery in sim | Notes |
|---|---|---|---|
| `LATE_NOTICE` | P0 already past ETA | 0% | Honesty / revised ETA |
| `REMAINING_LEG_UPGRADE` | P1 + eligible window/geo | versioned prevent rate | Freight-scaled **proxy** spend; human gate if cost ≥ $20 |
| `AT_RISK_NOTICE` | P1 ineligible or P2 | 0% OTIF; impact reduction only | CS / revised ETA |
| `NO_ACTION` | P3 | — | — |

Do not present net simulated $ as P&L. H9/H10 remain **simulation defaults** ([h9-h10-economics-gate.md](h9-h10-economics-gate.md)).

## Business read

- Lead with **exception queue + remaining-leg window**, not overall accuracy.
- Ranking is strong enough for a capacity-constrained NOC demo on a ~5% later-period miss rate.
- Temporal base-rate shift is a feature of the story (valid vs test), not something to hide.
- Agent **copies** the frozen NOC action (`noc-handoff-policy-v1`). It does not re-argmax EV.

## Appendix — superseded hero (ADR 0005 long-delivery)

Approval-time `long_delivery` (>14d duration) test PR-AUC **0.531** / ROC-AUC **0.796**, test base **20.4%**, precision @ 10% **64.7%**. Still the PIT source for `seller_late_rate_*`. Do not lead an interview with those numbers.

## Regenerate

```bash
uv run python -m olist_ml.training.pipeline --data-dir data/raw --trials 25
# then read artifacts/eval_report.json and artifacts/model_meta.json
```
