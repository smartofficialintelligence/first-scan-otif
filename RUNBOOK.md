# Runbook

Operational commands for local work and demo cost switches.

## Prerequisites

- Python 3.12 + `uv`
- GCP project + billing (for cloud demos)
- Terraform ≥ 1.5
- `gcloud` authenticated for human-driven applies (H7)

## Local (no GCP cost)

```text
make sync              # uv sync
make lint              # ruff
make typecheck         # mypy
make test              # unit/model/api
make fixtures          # regenerate data/fixtures
make train-local       # train from fixtures → artifacts/model.joblib
make train-pipeline    # validate → train → MLflow REGISTERED_CANDIDATE
make serve-local       # FastAPI on :8080
make smoke-local       # health + ready
make mcp-serve         # MCP tools over PredictionService
```

## Demo on / off

```text
make demo-up           # sync, ensure artifact, start local uvicorn (artifacts/api.pid)
make smoke-local
make demo-down         # stop local API; print GCP teardown reminders (no deletes)
make teardown-endpoint # Vertex undeploy dry-run (use --apply only with creds + H7 context)
```

## Feast

```text
make feast-apply       # apply + materialize (needs GCP creds; SQLite online demo-off)
make feast-historical  # offline retrieval sample
make feast-parity      # offline/online parity check
```

## Canary / replay

```text
make replay-baseline   # in-process replay → artifacts/prediction_logs.jsonl
make canary-bad        # create bad challenger + replay + canary_decide (expect ROLLBACK)
# or:
uv run python scripts/create_bad_challenger.py
uv run python scripts/replay_traffic.py --inprocess true --scenario bad_canary
uv run python scripts/canary_decide.py
```

Docs: [docs/m9-canary-replay.md](docs/m9-canary-replay.md)

## Airflow (local, no Composer)

```text
make airflow-train-local   # run_train_trigger() → local pipeline
make drift-check           # PSI/mean-shift stub → artifacts/drift_alarm.json
```

H5 (retrain) and H6 (promote) still required — no auto-promote.  
Docs: [docs/m10-airflow.md](docs/m10-airflow.md)

## Teardown

```text
make demo-down             # local API down
make teardown-endpoint     # Vertex dry-run / --apply when live
# Optional later: data-purge / Composer delete — never leave Composer/Redis/Endpoint overnight
```

### Human gates before costly actions

| Action | Gate |
|---|---|
| `terraform apply` | H7 — review plan, IAM, public exposure, persistent cost |
| Register/promote model | H3 / H4 / H6 |
| Monitoring-triggered retrain | H5 |
| Emergency rollback | H8 (can be same operator; must be logged) |

## Incident / rollback

1. Set traffic to champion 100% (canary_decide prints ROLLBACK recommendation)
2. Record `model_version`, time, reason in ops log / MLflow tag
3. `make demo-down` if the demo is over
4. Open follow-up: root cause (data, feature, model, infra)

## What “ready for interview demo” means

- `demo-up` → REST predict + model version returned  
- Feast online lookup visible (or explicitly documented offline-only mode)  
- MLflow run + registered model linked to Git SHA + snapshot  
- One canary replay with version attribution  
- `demo-down` completed; billing quiet  

## Do not

- Leave Composer or Memorystore running overnight
- Auto-promote challengers
- Commit credentials or SA JSON
- Run `terraform apply` from CI to production without H7
