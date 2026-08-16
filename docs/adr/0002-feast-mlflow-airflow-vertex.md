# ADR 0002: Feast + MLflow + Airflow + Vertex (train/serve)

## Status

Accepted — 2026-08-15  
Supersedes draft spec v0.2 choices of Vertex Feature Store, Vertex Experiments, and Vertex Model Registry as primary systems.

## Context

An all-Vertex ML lifecycle is coherent on GCP but less transferable and blurs ownership boundaries. The preferred portfolio narrative separates feature engineering, feature serving, orchestration, training, registry, and inference.

## Decision

| Concern | System |
|---|---|
| Feature engineering | dbt on BigQuery |
| Feature registry / offline / online | **Feast** (BQ offline, Redis online) |
| Orchestration / triggers | **Airflow** |
| Training DAG of ML steps | **Vertex AI Pipelines** |
| Experiments + model registry | **MLflow** |
| Online model deploy / traffic split | **Vertex AI Endpoint** |
| App APIs | FastAPI + MCP on Cloud Run |

## Consequences

- Clear resume story for each seam.
- More moving parts than Vertex-only — mitigated by milestone sequencing and demo-down teardown.
- Airflow hosting defaults to local/ephemeral; Composer only for live orchestration demos (cost).
- Original spec rule “do not add Airflow unless required” is **waived** — orchestration across Feast/MLflow/Vertex/monitoring is the requirement.
