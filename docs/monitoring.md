# Monitoring

Service and ML telemetry for the Olist promise-miss scorer.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/metrics` | JSON snapshot of in-process counters / latency summaries |
| GET | `/health` | Liveness |
| GET | `/ready` | Model artifact loaded |

Smoke:

```bash
make serve-local   # separate terminal
make metrics-smoke
```

## Signals exported today

**Service** (in-process + prediction logs)

- `predict_requests` / `predict_errors`
- `predict_latency_ms` — `sum`, `count`, `mean`
- replay log: `latency_ms`, `http_status`, `error_class`

**ML**

- `risk_band_counts` / `prediction_mix` — low / medium / high mix
- `stale_feature_rate` — increments when a predict observes stale online features (Feast SLA; see [gate-defaults.md](gate-defaults.md))
- **Feature PSI** on `geo_distance_km`, `seller_late_rate_*`, `seller_order_count_*`
- **Prediction drift** — high-band mix relative shift `> 20%`
- **Delayed-label quality** — PR-AUC / Brier on rows with `label_released=true` only

Implementation: `src/olist_ml/monitoring/` (`metrics.py`, `psi.py`, `drift.py`, `labels.py`, `delayed_eval.py`). Replay writes the log contract from `scripts/replay_traffic.py`.

## Prediction log contract

Minimum columns ([simulation.md](simulation.md)):

```text
event_id, order_id, snapshot_id, scenario, request_ts, model_version,
promise_miss_probability, risk_band, latency_ms, http_status,
feature_freshness_ts, feast_lookup_ms, error_class,
geo_distance_km, seller_late_rate_*, seller_order_count_*,
label_release_at, label_released, traffic_bucket, window
```

`feature_freshness_ts` / `feast_lookup_ms` are always present. When Feast is off they are `null` / `0`. `log_schema_complete` / `features_complete` flag missing keys vs that min list.

## Drift ≠ quality

Do **not** treat distribution shift as model failure.

| Signal class | Examples | What it means | Action |
|---|---|---|---|
| **Drift** (input / score mix) | Feature PSI, prediction drift (risk_band high-rate shift) | Serving population or score mix moved vs baseline | Alarm → **H5** → `retrain_trigger`. **Not** auto-rollback. |
| **Quality** (delayed labels) | Delayed-label PR-AUC vs rolling baseline / champion | Outcomes arrived; ranking/calibration actually worse | Canary gates / human promote (H4). See [gate-defaults.md](gate-defaults.md). |

Defaults (alarms and canary thresholds) live in **[gate-defaults.md](gate-defaults.md)**:

- Feature PSI `> 0.2`, prediction drift high-rate `> 20%` relative → retrain alarm only
- Delayed-label PR-AUC drop `> 0.03` vs baseline → quality alarm; canary uses `≥ champion − 0.02`

PSI and risk-band mix are early warning. PR-AUC (and Brier/ECE offline) are the quality bar.

## Delayed labels

Replay may store historical `label_promise_miss` immediately, but **`label_released` starts false**.

```text
label_release_at = prediction_timestamp + 7d
scripts/release_labels.py --virtual-now <demo clock>
scripts/evaluate_delayed.py   # released rows only
```

Canary quality (`scripts/canary_decide.py`) uses the delayed-eval report, not instant Brier on unreleased truth.

## Drift scenarios

`drift_seller_late` and `drift_geo` mutate holdout features before scoring ([simulation.md](simulation.md)). Compare a baseline log to a drifted log:

```bash
make drift-geo
# or: make drift-seller-late
cat artifacts/drift_alarm.json
```

An alarm is **not** a train start. Approve H5 then trigger retrain:

```bash
make approve-h5
make retrain-trigger
```

`make airflow-train-local` is the unconstrained M4 demo path and does **not** check H5.

## Dashboards (M8)

- **Local serving/ML:** `make export-monitoring` → `artifacts/monitoring_dashboard.json` (service + ML + last drift/delayed snapshots + `business_sim`).
- **Local business outcome (simulated):** `make decision-eval` → `artifacts/decision_impact.md` (action mix, deliveries moved late→on-time, delay-days avoided, spend). Same numbers under `business_sim` on `GET /v1/metrics`.
- **GCP:** `make gcp-up` applies `terraform/modules/monitoring` with Cloud Run. Tiles: request count, p95 latency, billable instance time, plus a text panel for PSI / delayed-label quality. **Not** a P&L chart. Destroyed by `make gcp-down`.

## Unit fixtures

`tests/unit/test_ops_contract.py` — named drift scenarios trip PSI `> 0.2`; unreleased labels are ignored; H5 is required before `reason=drift` retrain.
