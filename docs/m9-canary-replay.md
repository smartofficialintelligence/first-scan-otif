# Milestone 9 — Canary + replay + rollback

Implements the [simulation.md](simulation.md) contract locally (no live GCP required).

## Scripts

| Script | Role |
|--------|------|
| `scripts/replay_traffic.py` | Load `artifacts/replay_holdout.csv` (or build from fixtures via temporal split). Apply named scenarios (`baseline`, `drift_seller_late`, `drift_geo`, `bad_canary`). Score via in-process `PredictionService` (`--inprocess` default) or HTTP `--base-url`. Write `artifacts/prediction_logs.jsonl` with freshness, Feast lookup ms, PSI feature columns, `label_release_at`, `label_released=false`. |
| `scripts/create_drift_scenario.py` | Mutate a holdout CSV with the same named feature shifts. |
| `scripts/create_bad_challenger.py` | Copy champion artifact; degrade calibrated probabilities (`invert` / `swap` / `noise`). Write `artifacts/model_challenger_bad.joblib` + meta with `model_version` suffix `-bad`. |
| `scripts/release_labels.py` | Set `label_released` where `virtual_now >= label_release_at` (`prediction_ts + 7d`). |
| `scripts/evaluate_delayed.py` | PR-AUC / Brier on **released** rows only; quality alarm if drop `> 0.03`. |
| `scripts/canary_decide.py` | Latency + HTTP + **delayed-label** PR-AUC ≥ champion − 0.02. Instant ground truth is ignored until release. Rollback recommendation if gates fail. **Never auto-promote** (H4). |

## Traffic attribution (90/10)

```text
traffic_bucket = challenger if hash(order_id) % 10 == 0 else champion
```

Stable digest: SHA-256 of `order_id` (see `olist_ml.canary.split.traffic_bucket_for_order`).

## Local demo path

```bash
make train-local                    # ensures artifacts/model.joblib + replay_holdout.csv
make canary-bad
# create_bad_challenger → replay → release_labels (virtual now far future) → canary_decide
# → ROLLBACK / 100% champion recommendation (never auto-promote)
```

Makefile helpers:

```bash
make replay-baseline
make release-labels
make evaluate-delayed
make canary-bad
make drift-geo
```

## Gates

- Canary online gates: [gate-defaults.md](gate-defaults.md)
- Human gate **H4** required before any promote; this milestone only recommends rollback / hold.
- Decision script never changes traffic automatically.

## Acceptance

- [x] 90/10 version attribution (`tests/unit/test_canary_split.py`)
- [x] Bad challenger path yields ROLLBACK → 100% champion recommendation after delayed labels
- [x] Prediction logs include `model_version`, `feature_freshness_ts`, `feast_lookup_ms`, snapshot/scenario completeness, PSI feature columns, `label_release_at`
- [x] Drift scenario increments PSI above 0.2 (`tests/unit/test_ops_contract.py`)
