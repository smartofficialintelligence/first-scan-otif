# Monitoring

Service and ML telemetry for the Olist late-delivery risk scorer.

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

**Service**

- `predict_requests` / `predict_errors`
- `predict_latency_ms` — `sum`, `count`, `mean`

**ML**

- `risk_band_counts` / `prediction_mix` — low / medium / high mix
- `stale_feature_rate` — increments when a predict observes stale online features (Feast SLA; see [gate-defaults.md](gate-defaults.md))

Implementation: `src/olist_ml/monitoring/metrics.py`, recorded from `PredictionService.predict_one` / `explain_one`.

## Drift ≠ quality

Do **not** treat distribution shift as model failure.

| Signal class | Examples | What it means | Action |
|---|---|---|---|
| **Drift** (input / score mix) | Feature PSI, prediction drift (risk_band high-rate shift) | Serving population or score mix moved vs baseline | Alarm → investigate / schedule retrain (H5). **Not** auto-rollback. |
| **Quality** (delayed labels) | Delayed-label PR-AUC vs rolling baseline / champion | Outcomes arrived; ranking/calibration actually worse | Canary gates / human promote (H4). See [gate-defaults.md](gate-defaults.md). |

Defaults (alarms and canary thresholds) live in **[gate-defaults.md](gate-defaults.md)**:

- Feature PSI `> 0.2`, prediction drift high-rate `> 20%` relative → retrain alarm only
- Delayed-label PR-AUC drop `> 0.03` vs baseline → quality alarm; canary uses `≥ champion − 0.02`

PSI and risk-band mix are early warning. PR-AUC (and Brier/ECE offline) are the quality bar.
