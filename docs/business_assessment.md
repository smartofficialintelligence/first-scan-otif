# Business assessment: promise-miss at carrier handoff

**Hero product:** first-scan exception queue ([ADR 0006](adr/0006-handoff-promise-miss-noc.md)). The model exists to staff that queue, not to publish a leaderboard.

**Champion:** `local-20260821T203846Z` (100 Optuna trials; MLflow run `d1de28a2`; `snapshot_id=feast_historical`).  
**Target:** `promise_miss` = customer delivery after `order_estimated_delivery_date`.  
**Decision time:** `handoff_ts = order_delivered_carrier_date`.  
**Machine-readable:** `artifacts/eval_report.json` / `artifacts/model_meta.json` (gitignored).

Exec KPIs are **actions, late→on-time, delay-days, and $ under versioned simulation**. Ranking metrics are how we know the work list is better than a random draw. They are not the product. `allow_causal_roi_claims: false`. See [limitations-assumptions-proxies.md](limitations-assumptions-proxies.md).

---

## Business impact (holdout replay)

Chronological holdout that **never trains**: **n = 9,647** orders, **882** observed misses (9.1%). Champion `local-20260821T203846Z`, `econ-sim-v3`. Same seeds, three policies.

Ledger snapshot: [evidence/decision-impact-holdout-local-20260821T203846Z.md](evidence/decision-impact-holdout-local-20260821T203846Z.md).

| | Do nothing | Naive threshold (score ≥ 0.70, notice only) | **Frozen NOC policy (P0–P3)** |
|---|---:|---:|---:|
| Interventions (rate) | 0 | 332 (3.4%) | **603 (6.3%)** |
| Precision of interventions | | 94.6% | 69.8% |
| Observed misses reached | 0% | 35.6% | **47.7%** |
| Moved late → on-time | 0 | 0 | **25** |
| Delay-days avoided | 0 | 0 | **86.4** |
| Simulated spend | $0 | $332 | **$1,200** |
| Net simulated value | $0 | $1,089 | $916 |

### What to say out loud

- The cheap-notice baseline **wins on simulated net value and changes nothing physical**. Notices have 0% OTIF recovery in sim. They only send a message.
- The NOC policy is the **only** arm that upgrades a remaining leg (78 upgrades). That is the only way a late delivery becomes on-time in this simulation.
- That asymmetry is why the product is a **banded capacity rule**, not EV-argmax, and why intervention lift waits for an experiment on the action (switchback or A/B). This repo does not fake one.

### Frozen-policy action mix

| Action | Count | Role |
|---|---:|---|
| `LATE_NOTICE` | 196 | Already past the promise. Clock rule, not the ranker |
| `AT_RISK_NOTICE` | 329 | P1 ineligible or P2. Customer honesty; days late unchanged |
| `REMAINING_LEG_UPGRADE` | 78 | P1 + remaining window + geo. Only action that can flip OTIF in sim |
| `NO_ACTION` | 9,044 | P3. Scarce attention stays off the list |

Spend **≥ $20** waits for a person. Real emails, tickets, and carrier APIs stay off (`real_external_execution_enabled: false`).

### Simulation assumptions (not fitted lift)

```text
miss_cost     ≈ $10 + 10% of basket
upgrade_cost  ≈ freight-scaled placeholder (clip $5–$80)
notices       ≈ $1, 0% OTIF recovery
upgrade prevent rate ≈ 0.35   (assumed Bernoulli)
delay days    ≈ observed (delivery − EDD)+ ; 0 if the upgrade “succeeds”
```

Approved as simulation defaults ([h9-h10-economics-gate.md](h9-h10-economics-gate.md)). Do not present net simulated $ as P&L.

---

## Why this queue (supporting ranker)

Chronological **test set**: 14,471 orders, 4.6% miss rate. This is a different slice from the replay holdout above. Flag by predicted risk. Policy bands use **validation** score cutoffs, not these test-set percentiles.

| Capacity | Precision | Recall | Lift vs 4.6% base |
|---:|---:|---:|---:|
| Top 2.5% (P1-sized) | **46.0%** | 24.8% | **10.0×** |
| Top 10% (P2-sized) | **22.5%** | 49.6% | **4.9×** |

Among the highest-risk fortieth of test orders, about **2 in 5** actually miss the promise (**10.0×** a random draw). The top tenth captures about **half** of test misses. That is the capacity story: scarce attention, ranked work.

### Persisted policy thresholds (from validation scores)

| Band | Rule | Action |
|---|---|---|
| P0 | remaining days ≤ 0 | `LATE_NOTICE` |
| P1 | score ≥ **0.4895** | upgrade if eligible, else `AT_RISK_NOTICE` |
| P2 | score ≥ **0.2387** | `AT_RISK_NOTICE` |
| P3 | else | `NO_ACTION` |

P1 upgrade eligibility: `0 < remaining ≤ 7` days and (`geo ≥ 100 km` or not same state). Cutoffs travel in `model_meta.json`.

### Ranking / calibration (appendix)

| Metric | Test | Bootstrap 95% CI |
|---|---:|---|
| PR-AUC | **0.309** | 0.28 – 0.34 |
| ROC-AUC | **0.827** | |
| Brier | 0.037 | |
| ECE | 0.005 | |

This is **not** the ADR 0005 long-delivery ranker (test PR-AUC ~0.53 on a 20%+ duration label). Promise-miss is rarer and operationally the right OTIF question. Handoff clocks lift it well above the approval-time promise-miss baseline (~0.10–0.20).

### Base rate (temporal shift)

| Split | n | Misses | Base rate |
|---|---:|---:|---:|
| Train | 57,886 | 4,502 | **7.8%** |
| Valid | 14,471 | 1,773 | **12.3%** |
| Test | 14,471 | 669 | **4.6%** |
| Replay | 9,647 | 882 | **9.1%** |
| All labeled | 96,475 | 7,826 | **8.1%** |

Test miss rate is lower than train/valid. Compare precision to the **test** base rate. Policy thresholds are frozen on validation scores, so they are not re-fit to the test set.

---

## Business read

- Lead with **exception queue + remaining-leg window + simulated ops**, not overall accuracy.
- Ranking is strong enough to staff a small high-risk band on a 4.6% test miss rate.
- Simulated $ is a stakeholder conversation in cost-per-miss language. It is not unit-economics proof.
- Train / valid / test miss rates differ. Compare precision to the split you are quoting.
- Agent **copies** the frozen NOC action (`noc-handoff-policy-v1`). It does not re-argmax EV.

## Appendix: superseded hero (ADR 0005 long-delivery)

Approval-time `long_delivery` (>14d duration) test PR-AUC **0.531** / ROC-AUC **0.796**, test base **20.4%**, precision @ 10% **64.7%**. Still the PIT source for `seller_late_rate_*`. Do not lead an interview with those numbers.

## Regenerate

```bash
make decision-eval
# holdout snapshot: docs/evidence/decision-impact-holdout-local-20260821T203846Z.md
uv run python -m olist_ml.training.pipeline --data-dir data/raw --trials 25
# then read artifacts/eval_report.json and artifacts/model_meta.json
```
