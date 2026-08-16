# Target repository structure

Locked layout for implementation. Not all paths exist until their milestone.

```text
.
├── README.md
├── ARCHITECTURE.md
├── COST.md
├── RUNBOOK.md
├── pyproject.toml
├── uv.lock
├── Makefile
├── Dockerfile
├── .dockerignore
├── .env.example
│
├── src/olist_ml/
│   ├── config.py
│   ├── logging.py
│   ├── schemas.py
│   ├── data/
│   ├── features/          # contracts, assembler; Feast adapters
│   ├── training/          # tune, train, calibrate, evaluate, package, promote
│   ├── inference/         # predictor, preprocessing (shared with API)
│   ├── monitoring/
│   └── api/               # FastAPI + mcp_server
│
├── dbt/
├── feature_repo/          # Feast definitions (feature views, services)
├── airflow/               # DAGs: replay, drift, retrain, label release
├── pipelines/             # Vertex pipeline components + entrypoint
├── terraform/
│   ├── environments/dev/
│   └── modules/           # bigquery, gcs, vertex, feast_online, cloud_run,
│                          # mlflow, iam, monitoring, (optional composer)
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contracts/
│   ├── model/
│   └── api/
├── scripts/
│   ├── download_olist.py
│   ├── ingest_olist.py
│   ├── create_training_snapshot.py
│   ├── replay_traffic.py
│   ├── release_labels.py
│   ├── create_drift_scenario.py
│   ├── create_bad_challenger.py
│   ├── smoke_test.py
│   ├── demo_up.sh / demo_down.sh
│   └── teardown_endpoint.py
├── docs/
│   ├── LOCKED_DECISIONS.md
│   ├── ml-problem.md
│   ├── features.md
│   ├── simulation.md
│   ├── milestones.md
│   ├── repo-structure.md
│   ├── demo-script.md
│   ├── adr/
│   └── diagrams/
└── .github/workflows/
    ├── ci.yml
    ├── infra.yml
    ├── deploy-api.yml
    └── train-model.yml
```

## Notes

- Application deploy workflows must **not** always retrain models.
- `feature_repo/` and `airflow/` are first-class (not hidden inside notebooks).
- MLflow is a deployable service config under Terraform + optional `services/mlflow/` if needed later.
