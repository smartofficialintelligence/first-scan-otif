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

**Status:** implemented on `cursor/milestones-remaining-642f`.

dbt marts → Feast registry; offline retrieval for training; online seller features when demo-on (SQLite for demo-off).

**Accept:** entity lookup works; freshness visible; offline/online parity test exists.

See [m3-feast-setup.md](m3-feast-setup.md).

## Milestone 4 — Vertex training + MLflow

**Status:** implemented on `cursor/milestones-remaining-642f`.

Vertex Pipeline: validate → tune → train → calibrate → evaluate → log MLflow → register candidate.
Local path: `python -m pipelines.local_pipeline` / `make train-pipeline` (MLflow file store under `artifacts/mlruns`). Lifecycle stops at `REGISTERED_CANDIDATE` (no auto-promote).

**Accept:** one pipeline run produces a registered candidate with lineage metadata.

See [m4-training-mlflow.md](m4-training-mlflow.md).

## Milestone 5 — Managed inference

**Status:** implemented on `cursor/milestones-remaining-642f` (local REST + demo scripts + TF scaffolds; Vertex apply gated).

MLflow/champion artifact → Vertex Endpoint → Cloud Run FastAPI.

**Accept:** live REST predict; `model_version` returned; demo-down tears endpoint down.

See [m5-serving.md](m5-serving.md).

## Milestone 6 — MCP

**Status:** implemented on `cursor/milestones-remaining-642f`.

MCP tools call the same `PredictionService`.

**Accept:** agent-invokable predict/status without duplicated inference logic.

See [m6-mcp.md](m6-mcp.md).

## Milestone 7 — CI/CD + Terraform hardening

**Status:** implemented on `cursor/milestones-remaining-642f` (Terraform modules + validate path; deploy workflows may still expand).

PR CI (lint/type/test/dbt compile/tf validate/docker). Deploy workflows. H7 for apply.

**Accept:** PR checks green; infra reproducible from code.

## Milestone 8 — Monitoring

**Status:** implemented on `cursor/milestones-remaining-642f` (prediction logs + drift alarm stub; dashboards optional later).

Service + ML telemetry (latency, errors, drift, prediction mix, delayed-label quality).

**Accept:** dashboards or exported metrics show both service and ML signals; drift ≠ quality documented.

## Milestone 9 — Canary + replay + rollback

**Status:** implemented on `cursor/milestones-remaining-642f`.

Implements [simulation.md](simulation.md): baseline canary, bad challenger rollback, prediction logs.

**Accept:** 90/10 version attribution; bad canary rolls back to 100% champion.

See [m9-canary-replay.md](m9-canary-replay.md).

## Milestone 10 — Airflow triggers

**Status:** implemented on `cursor/milestones-remaining-642f`.

Schedule + drift/performance → candidate training pipeline; still requires H5/H6.

**Accept:** trigger produces candidate; no auto-promote.

See [m10-airflow.md](m10-airflow.md).

## Milestone 11 — Polish

**Status:** implemented on `cursor/milestones-remaining-642f`.

ARCHITECTURE/COST/RUNBOOK actuals placeholders, demo script, teardown commands verified locally.

**Accept:** interviewer can follow demo script end-to-end; idle cost ~$0 after down.

---

## Deferred — Decision + agentic action layer

**Status:** COMPLETE on `main` (D1–D13 + CI fixes + demo polish). Remaining human work: **sign H9/H10** when ready ([h9-h10-economics-gate.md](h9-h10-economics-gate.md)).

Full instruction set (D1–D13):  
[followup-decision-agentic-layer.md](followup-decision-agentic-layer.md)

**Shipped:** EV policy + ActionExecutor + ledger + replay + REST + MCP + LangGraph agent review + human gate + local evals + optional LangSmith + decision-eval Airflow stub + demo harness. Interviewer sequence: [demo-script.md](demo-script.md) Demo 7.
