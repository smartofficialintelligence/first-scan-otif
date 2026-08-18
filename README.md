# Olist Production ML

Public portfolio artifact: **promise-miss / OTIF exception scoring at first carrier scan** on the Olist Brazilian E-Commerce dataset, on **GCP**.

This is not a notebook demo. It is an end-to-end ML platform slice: features, training, registry, serving, canary, monitoring, cost-controlled teardown, plus a **decision / agent action layer** (deterministic NOC policy → LangGraph executes the frozen action → simulated interventions).

## Status

| Milestone | Status |
|---|---|
| M1 Local production model | implemented (`cursor/milestone-1-local-model-fd7a`) |
| M2 BigQuery + dbt | merged to `main` (PR #3) |
| M3 Feast | implemented on `cursor/milestones-remaining-642f` (SQLite demo-off) |
| M4 Vertex training + MLflow | implemented on `cursor/milestones-remaining-642f` (local pipeline + candidate registry) |
| M5 Managed inference | implemented on `cursor/milestones-remaining-642f` (local REST + TF scaffolds) |
| M6 MCP | implemented on `cursor/milestones-remaining-642f` |
| M7 CI/CD + Terraform hardening | implemented on `cursor/milestones-remaining-642f` |
| M8 Monitoring | implemented on `cursor/milestones-remaining-642f` (logs + drift stub) |
| M9 Canary + replay + rollback | implemented on `cursor/milestones-remaining-642f` |
| M10 Airflow triggers | implemented on `cursor/milestones-remaining-642f` (local DAGs; no Composer required) |
| M11 Polish | implemented on `cursor/milestones-remaining-642f` (docs/runbook/cost placeholders) |
| Decision + agent (D1–D13) | **complete** on `main` — simulation H9/H10 approved; causal ROI disallowed |
| Handoff NOC policy (ADR 0006) | this branch — promise-miss at carrier scan; agent copies policy |

Details: [docs/milestones.md](docs/milestones.md)

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

At **first carrier scan**, predict `P(promise_miss)` — customer delivery after the promised ETA ([ADR 0006](docs/adr/0006-handoff-promise-miss-noc.md)). API field: `promise_miss_probability`.

Policy bands P0–P3 are deterministic (already-late notice, remaining-leg upgrade proxy, at-risk notice, or no action). The agent does not choose policy. Simulated $ is **not** causal ROI.

Details: [docs/ml-problem.md](docs/ml-problem.md) · Assumptions: [docs/limitations-assumptions-proxies.md](docs/limitations-assumptions-proxies.md) · Business read: [docs/business_assessment.md](docs/business_assessment.md)

## Quick start (local)

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

Pipeline + canary (no GCP):

```bash
make train-pipeline
make canary-bad          # bad challenger → ROLLBACK recommendation
make airflow-train-local # local Airflow trigger (no Composer)
make demo-decision       # predict→policy→agent→sim harness (needs agent extra)
```

Optional full Olist (when download mirror works or CSVs are placed in `data/raw`):

```bash
make download-olist
make train-olist
```

## Cost posture

Demo resources are ephemeral:

- `make demo-up` — stand up billable path (local API today; GCP gated)
- `make demo-down` — tear down to ~$0/day idle

Policy: [COST.md](COST.md) · Ops: [RUNBOOK.md](RUNBOOK.md)

## Simulation

No organic traffic. Deterministic holdout replay drives canary, drift, and rollback demos.

Contract: [docs/simulation.md](docs/simulation.md) · Canary: [docs/m9-canary-replay.md](docs/m9-canary-replay.md)

Intervention “what-if” paths use a separate ActionExecutor with **versioned assumption economics** (not causal ROI). Interviewer walkthrough: [docs/demo-script.md](docs/demo-script.md).

## Build order

Vertical slices — see [docs/milestones.md](docs/milestones.md).

## Why not Databricks?

Transferable open seams + real GCP IaC/IAM/CI matter more here than a single lakehouse vendor. See [docs/adr/0001-gcp-not-databricks.md](docs/adr/0001-gcp-not-databricks.md).

## Human gates

Automation stops at risk-bearing steps (feature audit, promote, terraform apply, retrain approval). Listed in [docs/LOCKED_DECISIONS.md](docs/LOCKED_DECISIONS.md).
