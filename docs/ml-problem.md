# ML Problem Definition (H1)

Status: **locked** for implementation (2026-08-15).  
Changing these values requires an explicit human re-approval and an ADR amendment.

## Prediction problem

Predict whether an Olist order will be delivered **later than** the customer-facing estimated delivery date.

Operational use: risk-score newly approved orders so operations can prioritize proactive intervention.

## Prediction timestamp

```text
prediction_ts = order_approved_at
             ?? order_purchase_timestamp   -- fallback only if approval is null
```

All features must be knowable at `prediction_ts`. No aggregates may include the current order or any event at/after `prediction_ts`.

## Target

```text
late_delivery =
  order_delivered_customer_date > order_estimated_delivery_date
```

Type: binary `{0,1}` with positive class = late.

### Inclusion

- Delivered orders with non-null `order_delivered_customer_date`
- Non-null `order_estimated_delivery_date`
- Non-null `prediction_ts`

### Exclusion

- Cancelled / unavailable / invoiced-only orders without a customer delivery timestamp
- Rows where either side of the comparison is null
- Rows that cannot form a valid prediction timestamp

## Model output

```json
{
  "order_id": "...",
  "late_delivery_probability": 0.0,
  "risk_band": "low|medium|high",
  "model_version": "...",
  "prediction_timestamp": "...",
  "feature_timestamp": "..."
}
```

### Risk bands (initial defaults)

Configurable; initial cut points on calibrated probability:

| Band | Probability |
|---|---|
| low | `< 0.30` |
| medium | `0.30 – 0.60` |
| high | `≥ 0.60` |

Tune after first calibration study; do not hard-code forever in business logic without config.

## Fields unavailable at prediction time (blocklist)

Must never be used as features:

- `order_delivered_carrier_date`
- `order_delivered_customer_date` (label only)
- Review scores / review timestamps
- Any status transition after approval that encodes outcome
- Any seller/customer aggregate that includes the current order or future orders

## Metrics

### Offline primary

- **PR-AUC** (average precision)

### Offline secondary

- ROC-AUC
- Brier score
- Calibration error (ECE, fixed binning documented in eval code)
- Precision / recall / flagged volume at capacity thresholds (e.g. top 5%/10%/20% risk)
- Segment metrics: by customer state, seller state, product category (top-N), month

### Online / production

- Request rate, error rate, p50/p95/p99 latency
- Feature Store lookup latency / miss / stale rate
- Prediction distribution and risk-band mix
- Feature drift and prediction drift
- Delayed-label realized PR-AUC / Brier once labels release

**Drift ≠ performance degradation.** Monitoring must report both separately.

## Temporal splits

Chronological by `prediction_ts`:

| Split | Role |
|---|---|
| train | Fit + Optuna (inner temporal or stratified folds only within train window) |
| validation | Calibration / threshold selection |
| test | Final offline report |
| replay_holdout | Traffic simulation / canary (never used for training) |

Exact date cutoffs are derived from data extent at ingest time and written into the training snapshot manifest. Rule: **no future leakage across split boundaries**.

## Lineage required on every candidate

- Git SHA
- dbt project version / git SHA
- Feast feature views / feature service version
- Training snapshot ID
- Train/val/test/replay windows
- Optuna study ID / best params
- MLflow run ID + registered model version
