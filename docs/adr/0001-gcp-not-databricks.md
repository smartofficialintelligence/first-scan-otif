# ADR 0001: Stay on GCP (not Databricks)

## Status

Accepted — 2026-08-15

## Context

The portfolio artifact needs a production-ML story with transferable skills and a hard demo budget (~$75). Databricks Free Edition offers $0 managed lakehouse/MLflow surface area, which is attractive for cost.

## Decision

Build on **GCP**. Do not use Databricks (Free Edition or paid) as the runtime for this repository.

## Consequences

- We own seams explicitly: dbt, Feast, MLflow, Airflow, Vertex train/serve, Cloud Run.
- We must implement demo on/off switches to control idle cost.
- README may document “why not Databricks” as product judgment.
- Free Edition remains a valid personal learning path; it is out of scope for this artifact’s IaC/IAM/CI story.
