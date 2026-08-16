# Milestone 9 — Canary + replay + rollback

Implements the [simulation.md](simulation.md) contract locally (no live GCP required).

## Scripts

| Script | Role |
|--------|------|
| `scripts/replay_traffic.py` | Load `artifacts/replay_holdout.csv` (or build from fixtures via temporal split). Score via in-process `PredictionService` (`--inprocess` default) or HTTP `--base-url`. Write `artifacts/prediction_logs.jsonl`. |
| `scripts/create_bad_challenger.py` | Copy champion artifact; degrade calibrated probabilities (`invert` / `swap` / `noise`). Write `artifacts/model_challenger_bad.joblib` + meta with `model_version` suffix `-bad`. |
| `scripts/canary_decide.py` | Compare champion vs challenger error proxies in prediction logs. If challenger worse → **ROLLBACK** (100% champion). **Never auto-promote.** Exit 0 + JSON summary. |

## Traffic attribution (90/10)

```text
traffic_bucket = challenger if hash(order_id) % 10 == 0 else champion
```

Stable digest: SHA-256 of `order_id` (see `olist_ml.canary.split.traffic_bucket_for_order`).

## Local demo path

```bash
make train-local                    # ensures artifacts/model.joblib + replay_holdout.csv
uv run python scripts/create_bad_challenger.py
uv run python scripts/replay_traffic.py --inprocess true --scenario bad_canary
uv run python scripts/canary_decide.py
# → ROLLBACK recommendation when bad challenger is worse
```

Makefile helpers:

```bash
make replay-baseline
make canary-bad
```

## Gates

- Canary online gates: [gate-defaults.md](gate-defaults.md)
- Human gate **H4** required before any promote; this milestone only recommends rollback / hold.
- Decision script never changes traffic automatically.

## Acceptance

- [x] 90/10 version attribution (`tests/unit/test_canary_split.py`)
- [x] Bad challenger path yields ROLLBACK → 100% champion recommendation
- [x] Prediction logs include `model_version`, `order_id`, `proba`, `risk_band`, `traffic_bucket`
