# ADR 0005: Retarget to long-delivery risk

- Status: Accepted (**superseded as the hero product by [ADR 0006](0006-handoff-promise-miss-noc.md)**)
- Date: 2026-08-16
- Deciders: portfolio demo owner (Cloud Agent implementation with human merge)

## Context

The original H1 target (`promise_miss`: delivered after the customer-facing estimated date) is a weak-signal rare event on Olist (~8% overall, ~5% on the temporal test window). After a real feature/training iteration, test PR-AUC remained ~0.20 with ~19% precision @ 10% capacity — not credible for a production ML demo.

Olist estimated dates already absorb much of the geo/horizon structure, so “beat the promise” has little residual signal at approval time. Absolute delivery duration correlates strongly with distance, same-state, and seller history.

## Decision

Amend H1:

| Field | New locked value |
|---|---|
| Target | `long_delivery = (order_delivered_customer_date - prediction_ts) > 14 days` |
| Output | `P(long_delivery)` + risk band |
| API / MCP | `long_delivery_probability`; tools `predict_long_delivery`, `explain_long_delivery` |

Retain `promise_miss` as a diagnostic label only (not the training objective).

Historical feature columns named `seller_late_rate_*` continue to mean “prior positive-rate of the training target” (now long delivery) for online-contract stability.

## Consequences

- Demo metrics become usable (expected test PR-AUC ~0.45–0.50, precision@10% ~0.55–0.60 with current features).
- Story shifts from “missed ETA” to “slow delivery / long-haul SLA risk” — still ops-actionable at approval.
- Requires fixture regeneration, dbt label mart update, and model retrain.
- Supersedes the target row in `LOCKED_DECISIONS.md` / `ml-problem.md` for this artifact.
