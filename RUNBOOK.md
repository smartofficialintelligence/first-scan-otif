# Runbook

Operational commands for local work and demo cost switches.  
Makefile targets will be implemented with the code milestones; behavior below is **locked**.

## Prerequisites

- Python 3.12 + `uv`
- GCP project + billing (for cloud demos)
- Terraform ≥ 1.5
- `gcloud` authenticated for human-driven applies (H7)

## Local (no GCP cost)

```text
make sync              # uv sync
make lint              # ruff + typecheck
make test              # unit/model/api
make train-local       # train from local/sample Olist
make serve-local       # FastAPI on :8080
make smoke-local       # health + one predict
```

## Demo on / off

```text
make demo-up           # stand up billable demo path
make demo-smoke        # health, predict, optional MCP
make replay-baseline   # scripts/replay_traffic.py scenario=baseline
make replay-drift      # drift_seller_late
make canary-bad        # deploy bad challenger + replay + expect rollback
make demo-down         # tear down always-on resources → ~$0/day
make data-purge        # optional: drop BQ datasets
make data-restore      # GCS → BQ → dbt
```

### Human gates before costly actions

| Action | Gate |
|---|---|
| `terraform apply` | H7 — review plan, IAM, public exposure, persistent cost |
| Register/promote model | H3 / H4 / H6 |
| Monitoring-triggered retrain | H5 |
| Emergency rollback | H8 (can be same operator; must be logged) |

## Incident / rollback

1. Set Vertex traffic to champion 100%
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
