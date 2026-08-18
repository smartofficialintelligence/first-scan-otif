# ML Problem Definition (H1)

Status: **locked** for implementation (amended 2026-08-18 — [ADR 0006](adr/0006-handoff-promise-miss-noc.md)).  
Changing these values requires an explicit human re-approval and an ADR amendment.

ADR 0005 `long_delivery` (>14d from approval) is **not** the hero target. It remains a diagnostic label and the PIT source for `seller_late_rate_*`.

## Prediction problem

At **first carrier scan**, predict whether the order will **miss the customer-facing promise**.

Operational use: a fulfillment NOC queue. Seller work is done. Remaining-leg upgrade is a **demo proxy** when the remaining window and geography allow it; otherwise the action is notice / revised ETA. The agent executes the frozen policy action only.

## Prediction timestamp

```text
prediction_ts = order_approved_at
             ?? order_purchase_timestamp   -- approval clock (handling / horizon)
handoff_ts    = order_delivered_carrier_date   -- decision moment + split key
```

Customer delivery is **never** in X. Raw carrier timestamp is not in X; derived clocks are.

Historical features use events with `event_ts < handoff_ts` (strict).

## Target

```text
promise_miss = order_delivered_customer_date > order_estimated_delivery_date
```

Type: binary `{0,1}` with positive class = missed promise.

Diagnostic (not trained):

```text
delivery_days = order_delivered_customer_date - prediction_ts
long_delivery = delivery_days > 14
```

### Inclusion

- Delivered orders with non-null customer delivery date
- Non-null `order_estimated_delivery_date`
- Non-null `prediction_ts`
- Non-null `order_delivered_carrier_date` (`handoff_ts`)

### Exclusion

- Cancelled / unavailable / invoiced-only orders without a customer delivery timestamp
- Rows missing carrier scan (cannot score at handoff)
- Rows where either side of the comparison is null

## Model output

```json
{
  "order_id": "...",
  "promise_miss_probability": 0.0,
  "risk_band": "low|medium|high",
  "model_version": "...",
  "prediction_timestamp": "...",
  "feature_timestamp": "...",
  "target": "promise_miss_at_handoff",
  "p1_score_threshold": 0.0,
  "p2_score_threshold": 0.0
}
```

Online bands use **persisted validation score thresholds**, not live percentiles.

### Risk bands (initial defaults)

Configurable; initial cut points on calibrated probability:

| Band | Probability |
|---|---|
| low | `< 0.30` |
| medium | `0.30 – 0.60` |
| high | `≥ 0.60` |

Separate from policy bands P0–P3 (see ADR 0006).

## Fields unavailable as raw features (blocklist)

Must never be used as model-matrix columns:

- `order_delivered_carrier_date` (derive clocks only)
- `order_delivered_customer_date`
- Review score / comment / review timestamps
- Anything after `handoff_ts`

Allowed derived (knowable at scan): `handling_days`, `remaining_to_promise_days`, `handling_frac_of_promise`, `limit_miss`.
