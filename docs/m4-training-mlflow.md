# Milestone 4 setup (Vertex training + MLflow)

## What this milestone adds

- Local orchestrator: `pipelines/local_pipeline.py`  
  Steps: validate → tune → train → calibrate → evaluate → log MLflow → register candidate
- Components: `pipelines/components.py` (plain Python; no live Vertex required)
- MLflow registry helper: `olist_ml.registry.mlflow_registry`  
  Model name `olist-late-delivery`; tags `lifecycle_state=REGISTERED_CANDIDATE`, `model_version`
- Offline gates: `olist_ml.training.gates.offline_promotion_checks` (see `docs/gate-defaults.md`)
- Vertex stub: `pipelines/vertex_pipeline.py` (compile-or-skip without GCP SDK)

Lifecycle terminal state for this milestone: **REGISTERED_CANDIDATE** (human gates H3+ before canary).

## Prerequisites

1. `uv sync --all-extras` (installs `ml` extra → `mlflow>=2.14.0`)
2. Fixture or raw Olist CSVs under `--data-dir`

## Tracking URI

Default local backend (SQLite — FileStore is flaky on MLflow 3.x):

```text
MLFLOW_TRACKING_URI=sqlite:///./artifacts/mlflow.db
```

`file:` URIs still work if you set `MLFLOW_ALLOW_FILE_STORE=true`, but prefer SQLite for local demos.

Override with env var for a remote MLflow server. Do not put GCP project ids in source — use `GCP_PROJECT_ID`, `GCP_REGION`, `VERTEX_PIPELINE_ROOT`.

## Commands

```bash
uv sync --all-extras
make train-pipeline
# or
uv run python -m pipelines.local_pipeline --data-dir data/fixtures --trials 3
uv run python scripts/run_train_pipeline.py --data-dir data/fixtures --trials 3

# Vertex compile stub (skips cleanly if google-cloud-aiplatform missing)
uv run python -m pipelines.vertex_pipeline
```

## Accept criteria

| Check | How |
|---|---|
| Pipeline produces registered candidate | `make train-pipeline` → MLflow run + model `olist-late-delivery` |
| Lineage / lifecycle tags | `lifecycle_state=REGISTERED_CANDIDATE`, `model_version` on run |
| No auto-promote | Gates helper exists; pipeline does not set `APPROVED_FOR_CANARY` |
| Vertex optional | `pipelines.vertex_pipeline` prints skip or writes stub JSON |
