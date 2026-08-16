# Olist Production ML

Public portfolio artifact: production-grade late-delivery risk scoring on the Olist Brazilian E-Commerce dataset, on **GCP**.

This is not a notebook demo. It is an end-to-end ML platform slice: features, training, registry, serving, canary, monitoring, and cost-controlled teardown.

## Status

**Milestone 1 complete (local):** train → evaluate → serialize → FastAPI predict, with tests.  
**Milestone 2 in progress (PR #3):** dbt + Terraform wired for live BigQuery. Fixture ingest + `dbt build` green; `terraform apply` awaits H7. See [docs/m2-gcp-setup.md](docs/m2-gcp-setup.md).

## Locked architecture (short)

| Layer | Choice |
|---|---|
| Warehouse / transforms | BigQuery + dbt |
| Feature store | Feast (BQ offline, Redis online for demos) |
| Orchestration | Airflow |
| Training | Vertex AI Pipelines (XGBoost + Optuna) |
| Experiments / registry | MLflow |
| Model serving | Vertex AI Endpoint |
| App APIs | FastAPI on Cloud Run (REST + MCP) |

Full diagram: [ARCHITECTURE.md](ARCHITECTURE.md)  
Binding decisions: [docs/LOCKED_DECISIONS.md](docs/LOCKED_DECISIONS.md)

## ML problem

At order approval time, predict `P(order delivered after the estimated delivery date)`.

Details: [docs/ml-problem.md](docs/ml-problem.md)

## Quick start (Milestone 1)

```bash
make sync
make fixtures
make test
make train-local
make serve-local
# other terminal:
curl -s localhost:8080/health
curl -s localhost:8080/ready
```

Optional full Olist (when download mirror works or CSVs are placed in `data/raw`):

```bash
make download-olist
make train-olist
```

## Cost posture

Demo resources are ephemeral:

- `make demo-up` — stand up billable path (later milestones)
- `make demo-down` — tear down to ~$0/day idle

Policy: [COST.md](COST.md) · Ops: [RUNBOOK.md](RUNBOOK.md)

## Simulation

No organic traffic. Deterministic holdout replay drives canary, drift, and rollback demos.

Contract: [docs/simulation.md](docs/simulation.md)

## Build order

Vertical slices — see [docs/milestones.md](docs/milestones.md).

## Why not Databricks?

Transferable open seams + real GCP IaC/IAM/CI matter more here than a single lakehouse vendor. See [docs/adr/0001-gcp-not-databricks.md](docs/adr/0001-gcp-not-databricks.md).

## Human gates

Automation stops at risk-bearing steps (feature audit, promote, terraform apply, retrain approval). Listed in [docs/LOCKED_DECISIONS.md](docs/LOCKED_DECISIONS.md).
