# Data & Traffic Simulation Contract

Status: **locked** for Milestone 9+ implementation.  
Related: [ml-problem.md](ml-problem.md), [LOCKED_DECISIONS.md](LOCKED_DECISIONS.md).

## Principles

1. Use **real Olist orders** as events — do not invent customers/orders for the core path.
2. Simulation exists because there is **no organic production traffic**.
3. Every replay is **deterministic** given a seed and snapshot ID.
4. Champion/challenger comparison uses the **same** replay inputs.

## Dataset roles

After ingest + label construction, assign splits by `prediction_ts`:

| Split | Fraction (initial) | Use |
|---|---|---|
| train | ~60% earliest | Train + Optuna |
| validation | ~15% | Calibration / thresholds |
| test | ~15% | Offline report |
| `replay_holdout` | ~10% latest | Traffic replay, canary, delayed-label demo |

Exact cut dates are frozen in `snapshots/<snapshot_id>/manifest.json`.

## Replay event schema

Each replay message is a FastAPI `POST /v1/predict` body:

```json
{
  "order_id": "string",
  "seller_id": "string",
  "purchase_timestamp": "ISO-8601",
  "prediction_timestamp": "ISO-8601",
  "item_count": 1,
  "basket_value": 0.0,
  "freight_value": 0.0,
  "seller_count": 1,
  "category_count": 1,
  "payment_type_primary": "string",
  "installment_count": 1,
  "estimated_delivery_horizon_days": 0,
  "customer_state": "string",
  "seller_state_primary": "string",
  "geo_distance_km": 0.0,
  "replay": {
    "scenario": "baseline|drift_seller_late|drift_geo|bad_canary",
    "seed": 42,
    "snapshot_id": "string",
    "label_release_at": "ISO-8601"
  }
}
```

Request-native fields must match the feature contract. Seller historical features are **not** trusted from the client when Feast online is enabled — they are looked up server-side.

## Traffic shape

| Parameter | Default | Notes |
|---|---|---|
| `seed` | `42` | Global deterministic shuffle within holdout |
| `qps` | `5` | Sustained requests/sec for demo |
| `duration` / `max_events` | holdout size or cap `2000` | Whichever smaller for cheap demos |
| `concurrency` | `4` | Async client workers |
| Order | Sorted by `prediction_timestamp` ascending after seeded tie-break | Preserves time order |

Script: `scripts/replay_traffic.py`  
Emits: prediction log rows (BQ or GCS JSONL) with model version, latency, status, features hash, probability.

### Prediction log (minimum columns)

```text
event_id, order_id, snapshot_id, scenario, request_ts, model_version,
long_delivery_probability, risk_band, latency_ms, http_status,
feature_freshness_ts, feast_lookup_ms, error_class
```

## Label delay simulation

Ground truth exists historically, but demos must show **delayed labels**:

```text
label_release_at = prediction_timestamp + label_delay
default label_delay = 7 days
```

- During replay: write predictions immediately.
- `scripts/release_labels.py` (or Airflow task): mark labels available where `demo_now >= label_release_at`.
- Evaluation job joins released labels only.

For short live demos, `demo_now` may be a configurable virtual clock so a 7-day delay can be exercised in minutes.

## Scenarios

### `baseline`

Unmodified holdout features. Used for healthy canary promotion demos.

### `drift_seller_late`

On a configurable fraction of events (default 30%), shift seller online features:

- Multiply `seller_late_rate_*` by `1.5` (cap 1.0) **in the online store / shadow feed**, or
- Prefer: materialize a Feast batch with shifted seller stats for a known seller cohort.

Goal: feature drift alarms fire; may or may not move delayed-label metrics — report both.

### `drift_geo`

Inflate `geo_distance_km` by +50% on 30% of events (request-native drift).

### `bad_canary`

Deploy challenger artifact from `scripts/create_bad_challenger.py`:

- Same feature schema
- Intentionally weak (e.g. underspecified tree / shuffled-label trained / heavily regularized stub)
- Must fail configured quality or latency gates → rollback to champion 100%

## Canary flow (locked)

```text
champion v1 = 100%
  → deploy challenger v2
  → traffic 90/10
  → replay baseline
  → delayed-label compare
  → H4 human approval
  → v2 = 100%  OR  rollback
```

Failed path uses `bad_canary` challenger and must end at champion 100%.

## Airflow hooks (simulation-aware)

| DAG / task | Input | Output |
|---|---|---|
| `replay_canary` | scenario, snapshot_id, seed | prediction logs |
| `release_labels` | virtual_now | labels available flag |
| `evaluate_delayed` | logs + labels | metrics vs gates |
| `drift_check` | recent features/preds | drift scores / alarms |
| `retrain_trigger` | alarm + H5 approval flag | Vertex pipeline run |

No auto-promote. Alarms open candidates or notifications only.

## Acceptance tests for simulation

- Same `seed` + `snapshot_id` → identical request order and bodies
- Replay never includes train/val/test order_ids
- Prediction logs always include `model_version`
- `bad_canary` scenario fails gates in CI (with local stub endpoint acceptable in unit/contract tests)
- Drift scenario increments drift metric above threshold in a unit/integration fixture

## Non-goals

- Multi-region traffic
- Mobile/web client simulation
- Adversarial bot traffic
- Generating a parallel fake Olist population
