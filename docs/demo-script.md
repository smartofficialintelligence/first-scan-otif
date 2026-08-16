# Demo script

Locked sequence for interview / portfolio recording. Prefer local commands first; GCP steps need H7 and secrets.

## Prep (day of)

1. Confirm prior `make demo-down`
2. `make sync && make fixtures && make test`
3. `make demo-up` (local uvicorn) → `make smoke-local`

## Demo 1 — Features

```bash
# dbt (needs GCP):
make ingest-fixtures-bq && make dbt-build
# Feast (needs GCP; SQLite online demo-off):
make feast-apply && make feast-historical
```

## Demo 2 — Train

```bash
make train-pipeline
# or: make airflow-train-local
# Show artifacts/mlruns + REGISTERED_CANDIDATE (not champion)
```

## Demo 3 — Serve

```bash
curl -s localhost:8080/health
curl -s localhost:8080/ready
curl -s localhost:8080/v1/model
# POST /v1/predict  |  make mcp-serve → predict_long_delivery
# Response includes model_version
```

## Demo 4 — Canary

```bash
make replay-baseline
# Inspect artifacts/prediction_logs.jsonl — traffic_bucket + model_version
```

## Demo 5 — Rollback

```bash
make canary-bad
# create_bad_challenger → replay → canary_decide
# Expect ROLLBACK → 100% champion recommendation (never auto-promote)
```

## Demo 6 — Drift / retrain

```bash
make drift-check
cat artifacts/drift_alarm.json
# H5 → make airflow-train-local / train-pipeline → new candidate
# H6 required before promote
```

## Demo 7 — Cost / teardown

```bash
make demo-down
make teardown-endpoint   # dry-run unless --apply with live Vertex
# Fill COST.md actuals table after paid demo
```

**Never** skip human gates in the recorded story — show the approval step even if it is a CLI confirm.
