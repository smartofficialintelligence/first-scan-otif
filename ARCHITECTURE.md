# Architecture

This document is the runtime architecture for the Olist production-ML portfolio artifact.  
Binding decisions: [docs/LOCKED_DECISIONS.md](docs/LOCKED_DECISIONS.md).

## Goal

Demonstrate end-to-end production ML engineering on GCP using the public Olist Brazilian E-Commerce dataset — not notebook training.

## Component diagram

```text
                               GitHub
                                 │
                          GitHub Actions
                    test / lint / build / deploy
                                 │
                             Terraform
                                 │
                                 ▼
                           GCP Project
                                 │
        ┌────────────────────────┼─────────────────────────┐
        │                        │                         │
     BigQuery              Artifact Registry          Cloud Run
        │                        │                         │
       dbt                  Docker images                │
        │                                                  │
 staging / intermediate / feature marts                    │
 contracts / tests                                         │
        │                                                  │
        ▼                                                  │
   Feast Feature Store / Registry                           │
   ├── offline store: BigQuery                              │
   └── online store: Memorystore Redis (demo-on only)       │
        │                                                  │
        ├───────────────┐                                  │
        │               │                                  │
        ▼               ▼                                  │
 training dataset   online feature lookup                  │
        │               │                                  │
        ▼               │                                  │
                     Airflow                               │
        ┌────────────────┼─────────────────────────────┐    │
        │                │                             │    │
   scheduled jobs    drift/performance checks      retraining DAG
        │                │                             │
        │                └──────────────┐              │
        │                               │              │
        ▼                               ▼              ▼
                    Vertex AI Training Pipeline
        ┌──────────────────┼───────────────────┐
        │                  │                   │
     validate            train              evaluate
                           │
                   XGBoost + Optuna
                           │
                           ▼
                         MLflow
                  ┌────────┴─────────┐
                  │                  │
             Experiments       Model Registry
                  │                  │
                  └────────┬─────────┘
                           │
                    model candidate
                           │
                  quality promotion gate
                           │
                           ▼
                 champion / challenger
                           │
              ┌────────────┴────────────┐
              │                         │
         champion v1               challenger v2
              │                         │
              └────── Vertex Endpoint ──┘
                      90 / 10 split
                           │
                           ▼
                  FastAPI / Cloud Run
                    REST + MCP
                           │
                           ▼
                 synthetic traffic replay
                           │
              ┌────────────┴────────────┐
              │                         │
       service telemetry           ML telemetry
       latency / errors           feature drift
       throughput                 prediction drift
                                  delayed-label quality
              │                         │
              └────────────┬────────────┘
                           │
                     Airflow decision
                           │
              ┌────────────┴────────────┐
              │                         │
        promote / rollback       trigger retraining
                                      │
                                      └────→ Vertex AI Pipeline
```

## Separation of concerns

| Layer | System | Responsibility |
|---|---|---|
| Feature engineering | dbt | Point-in-time feature tables, tests, contracts |
| Feature serving | Feast | Registry, offline training retrieval, online entity lookup |
| Orchestration | Airflow | Schedules, drift checks, retrain triggers, cross-system DAGs |
| Training workflow | Vertex AI Pipelines | validate → tune → train → calibrate → evaluate |
| Tracking / registry | MLflow | Experiments, artifacts, model versions, aliases |
| Model inference | Vertex AI Endpoint | Managed deploy, traffic split |
| App boundary | FastAPI + MCP | Auth, validation, assembly, telemetry |

This is intentionally **not** an all-Vertex lifecycle. Vertex owns training jobs and endpoints; open tooling owns features, tracking, and orchestration.

## Data path

```text
GCS (canonical raw when idle)
  → load to BigQuery raw (demo-up)
  → dbt staging / intermediate / marts/ml
  → Feast apply + materialize offline
  → (demo-on) materialize online to Redis
  → training snapshot → Vertex Pipeline → MLflow candidate
  → Vertex Endpoint ← FastAPI PredictionService
```

## Inference path

```text
Client (REST or MCP)
  → FastAPI
  → PredictionService
       ├─ request-native features (basket, timestamp, etc.)
       ├─ Feast online get(seller_id, ...) when online store is up
       └─ Vertex Endpoint predict
  → response with probability, risk_band, model_version, timestamps
```

## Cost posture

Always-on managed resources are **demo-scoped**. See [COST.md](COST.md) and `make demo-up` / `make demo-down` in [RUNBOOK.md](RUNBOOK.md).

## Key paths (this branch)

| Concern | Path |
|---|---|
| Local / Vertex training pipeline | `pipelines/` (`local_pipeline.py`, `vertex_pipeline.py`) |
| MLflow candidate registry | `src/olist_ml/registry/` |
| Feast repo | `feature_repo/` |
| Canary replay / bad challenger / decide | `scripts/replay_traffic.py`, `scripts/create_bad_challenger.py`, `scripts/canary_decide.py` |
| Traffic attribution | `src/olist_ml/canary/` |
| Airflow DAGs (local-first) | `airflow/dags/olist_train_dag.py`, `airflow/dags/olist_drift_dag.py` |
| MCP | `src/olist_ml/api/mcp_server.py` |
| Demo up/down | `scripts/demo_up.sh`, `scripts/demo_down.sh` |
| Milestone notes | `docs/m3-feast-setup.md` … `docs/m10-airflow.md` |

## Out of scope

- Kubernetes, Kafka, Spark (unless a real requirement appears later)
- Databricks
- Organic production user traffic (use replay simulation instead)
