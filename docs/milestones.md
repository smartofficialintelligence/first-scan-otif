# Milestones

Binding build order. Each milestone ends in a **runnable** path. Do not scaffold the full cloud stack first.

## Milestone 1 — Local production model

**Status:** implemented on branch `cursor/milestone-1-local-model-fd7a`.

**In scope:** uv/pyproject, src layout, local Olist load, target construction, temporal split, Optuna+XGBoost, calibration, eval, serialize, shared `PredictionService`, FastAPI `/health` `/ready` `/v1/predict`, tests, Dockerfile, Makefile, README.

**Out of scope:** GCP, dbt, Feast, MCP, Airflow, Terraform apply.

**Accept:** no notebook dependency; tests pass; deterministic inference for fixed artifact.

## Milestone 2 — BigQuery + dbt

**Status:** merged to `main` (PR #3). Infra applied; fixture ingest + dbt build; datasets aligned (`staging` / `intermediate` / `ml`).

Raw → BQ → dbt staging/intermediate/marts → training table + tests.

**Accept:** dbt tests pass; H2 feature review scheduled/completed for shipped features.

## Milestone 3 — Feast

**Status:** in progress on `cursor/milestone-3-feast-642f`.

dbt marts → Feast registry; offline retrieval for training; online seller features when demo-on (SQLite for demo-off).

**Accept:** entity lookup works; freshness visible; offline/online parity test exists.

## Milestone 4 — Vertex training + MLflow

Vertex Pipeline: validate → tune → train → calibrate → evaluate → log MLflow → register candidate.

**Accept:** one pipeline run produces a registered candidate with lineage metadata.

## Milestone 5 — Managed inference

MLflow/champion artifact → Vertex Endpoint → Cloud Run FastAPI.

**Accept:** live REST predict; `model_version` returned; demo-down tears endpoint down.

## Milestone 6 — MCP

MCP tools call the same `PredictionService`.

**Accept:** agent-invokable predict/status without duplicated inference logic.

## Milestone 7 — CI/CD + Terraform hardening

PR CI (lint/type/test/dbt compile/tf validate/docker). Deploy workflows. H7 for apply.

**Accept:** PR checks green; infra reproducible from code.

## Milestone 8 — Monitoring

Service + ML telemetry (latency, errors, drift, prediction mix, delayed-label quality).

**Accept:** dashboards or exported metrics show both service and ML signals; drift ≠ quality documented.

## Milestone 9 — Canary + replay + rollback

Implements [simulation.md](simulation.md): baseline canary, bad challenger rollback, prediction logs.

**Accept:** 90/10 version attribution; bad canary rolls back to 100% champion.

## Milestone 10 — Airflow triggers

Schedule + drift/performance → candidate training pipeline; still requires H5/H6.

**Accept:** trigger produces candidate; no auto-promote.

## Milestone 11 — Polish

ARCHITECTURE/COST/RUNBOOK actuals, demo script, screenshots, teardown verified.

**Accept:** interviewer can follow demo script end-to-end; idle cost ~$0 after down.
