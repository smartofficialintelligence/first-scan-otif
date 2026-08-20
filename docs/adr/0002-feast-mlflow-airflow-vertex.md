# ADR 0002: Feast + MLflow + Airflow + Vertex (train/serve)

## Status

Accepted — 2026-08-15  
Supersedes draft spec v0.2 choices of Vertex Feature Store, Vertex Experiments, and Vertex Model Registry as primary systems.

## Context

An all-Vertex ML lifecycle is coherent on GCP but less transferable and blurs ownership boundaries. The preferred portfolio narrative separates feature engineering, feature serving, orchestration, training, registry, and inference.

## Decision

| Concern | System | Wired as of 2026-08-20 |
|---|---|---|
| Feature engineering | dbt on BigQuery | **Yes** — raw CSVs land in GCS, BigQuery loads from those objects, dbt builds the marts |
| Feature registry / offline / online | **Feast** (BQ offline, **SQLite online**). Redis remains the production choice for a shared low-latency store across serving replicas; skipped here for demo cost. | **Yes, in the deployed request path** — the serving image ships the Feast client and the materialized store; warmed at startup, fails open |
| Training input | dbt snapshot / Feast historical | **Yes, when exported** — a complete training snapshot replaces the training table; otherwise Feast history overlays seller columns on `(seller_id, handoff_ts)` |
| Orchestration / triggers | **Airflow** | **Partly** — DAG files run as local CLIs; the `airflow` extra makes the DAG objects real for a local scheduler. No Composer |
| Training DAG of ML steps | Vertex AI Pipelines | **No** — `pipelines/vertex_pipeline.py` is a compile-or-skip stub. The local pipeline is the real step graph |
| Experiments + model registry | **MLflow** | **Yes, on the champion path** — every train registers a candidate tagged with `git_sha` and `snapshot_id`. Local SQLite backend; no shared tracking server |
| Online model deploy / traffic split | Vertex AI Endpoint | **No** — flag defaults off and would create an empty endpoint. Serving is the joblib baked into the Cloud Run image; the 90/10 canary is replay attribution, not a Cloud Run traffic split |
| App APIs | FastAPI + MCP on Cloud Run | **Yes** — one `PredictionService` behind both |

## Consequences

- Clear resume story for each seam.
- More moving parts than Vertex-only — mitigated by milestone sequencing and demo-down teardown.
- Airflow hosting defaults to local/ephemeral; Composer only for live orchestration demos (cost).
- Original spec rule “do not add Airflow unless required” is **waived** — orchestration across Feast/MLflow/monitoring is the requirement.
- **The two Vertex rows stay honest as "named, not wired."** They are in this ADR because they were the considered alternative, not because the repo runs them. Anything this table marks "No" must not be described as live anywhere else in the repo.
