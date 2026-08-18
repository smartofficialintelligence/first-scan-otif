# ADR 0006: Promise-miss at carrier handoff (NOC exception policy)

- Status: Accepted
- Date: 2026-08-18
- Deciders: portfolio demo owner
- Supersedes: [ADR 0005](0005-long-delivery-target.md) as the **hero product** (long_delivery remains a diagnostic / PIT rate source)

## Context

ADR 0005 trained `long_delivery = (delivered − approval) > 14d`. That target is **duration**, not a broken customer promise. On Olist, most >14d orders were already promised >14d, so the model largely reconstructed ETA. Promise-miss at **approval** is weak (~0.22 PR-AUC) because the public estimate already absorbs geo/horizon.

The operational moment that matches a fulfillment NOC is **first carrier scan** (`order_delivered_carrier_date`): the seller is done; remaining-leg exception handling can start. At that scan, clocks that are illegal at approval become legal: handling time, days remaining to the promise, and whether the seller missed `shipping_limit_date`.

A leakage-safe experiment on that label + clocks reached test **PR-AUC 0.308 / ROC 0.826** (n=14,403, 4.69% miss). Queue precision at top 2.5% / 10% of the later test book is the capacity story — not a calendar “10% of days.”

## Decision

| Field | Locked value |
|---|---|
| Decision point | First carrier scan (`handoff_ts = order_delivered_carrier_date`) |
| Approval clock | `prediction_ts = order_approved_at` (fallback purchase) — used for handling/horizon, not the split |
| Target | `promise_miss = customer_delivery > order_estimated_delivery_date` |
| Split | Chronological on `handoff_ts` |
| Output | `P(promise_miss)` + risk band; API field `promise_miss_probability`; `target=promise_miss_at_handoff` |
| Added features | `handling_days` (clip ≥ −1), `remaining_to_promise_days`, `handling_frac_of_promise`, `limit_miss` |
| Blocked raw columns | `order_delivered_carrier_date`, `order_delivered_customer_date` still must not enter X |
| Policy | Deterministic bands P0–P3 (not EV-argmax). Agent copies `recommended_action` |
| Upgrade | Demo proxy `REMAINING_LEG_UPGRADE` only if P1 **and** `0 < remaining ≤ 7` **and** (`geo ≥ 100km` or not same state) |
| Economics | Versioned simulation; `allow_causal_roi_claims: false` |

Online serving stores **validation score thresholds** (`p1_score_threshold`, `p2_score_threshold` on `ModelMeta`), not live percentiles.

`seller_late_rate_*` remains a **duration** (long_delivery) PIT rate. That combination is what the handoff screen used; names stay for Feast contract stability.

## Policy bands

| Band | Rule | Action |
|---|---|---|
| P0 | `remaining_to_promise_days ≤ 0` | `LATE_NOTICE` (already late; not a ranker) |
| P1 | score ≥ p1 threshold (~top 2.5% of validation scores) | Upgrade if eligible, else `AT_RISK_NOTICE` |
| P2 | p1 > score ≥ p2 (~top 10%) | `AT_RISK_NOTICE` only |
| P3 | else | `NO_ACTION` |

Human approval only when `upgrade_cost ≥ 20` (spend risk). Notices have **0 OTIF recovery** in simulation.

## Consequences

- Demo language is OTIF / exception / remaining-leg — not “long haul SLA at approval.”
- Requires fixture regeneration, dbt label/feature update, model retrain, and policy YAML v3.
- Upgrade cost is a freight-scaled **placeholder**; see [limitations-assumptions-proxies.md](../limitations-assumptions-proxies.md).
