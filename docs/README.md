# Documentation

The [root README](../README.md) is the landing page. This index is the rest of the system, grouped the way a hiring conversation usually goes.

**Suggested read:** [README](../README.md) (2 min) → [business_assessment.md](business_assessment.md) (impact, then ranker) → [ARCHITECTURE.md](../ARCHITECTURE.md) (interview walk).

---

## Problem and product

What is scored, when, and what action the score is allowed to trigger.

| Doc | What it answers |
|---|---|
| [ml-problem.md](ml-problem.md) | Locked prediction problem, clocks, label, inclusion rules |
| [ADR 0006 — handoff promise-miss NOC](adr/0006-handoff-promise-miss-noc.md) | Why first scan, why not duration, why not EV-argmax |
| [features.md](features.md) | Feature groups, point-in-time rules, leakage audit |
| [h2-feature-audit.md](h2-feature-audit.md) | Formal accept of the v1 feature set |
| [limitations-assumptions-proxies.md](limitations-assumptions-proxies.md) | What is measured vs assumed vs proxied |
| [LOCKED_DECISIONS.md](LOCKED_DECISIONS.md) | Binding table of product and platform choices |

## Impact and model quality

| Doc | What it answers |
|---|---|
| [business_assessment.md](business_assessment.md) | Business impact first: action mix, late→on-time, spend, then queue lift and ranking |
| [evidence/decision-impact-holdout-local-20260821T203846Z.md](evidence/decision-impact-holdout-local-20260821T203846Z.md) | Current-champion holdout replay: action mix, late→on-time, spend |
| [evidence/decision-impact-holdout.md](evidence/decision-impact-holdout.md) | Prior-champion snapshot (kept for comparison) |
| [gate-defaults.md](gate-defaults.md) | Offline promote/canary numeric gates |
| [eval_iteration_notes.md](eval_iteration_notes.md) | How the published champion was iterated |
| [experiments/](experiments/) | Earlier targets (duration, approval-time miss, overrun) |

## Serving, agents, and API

| Doc | What it answers |
|---|---|
| [m5-serving.md](m5-serving.md) | Local uvicorn and Cloud Run path |
| [m6-mcp.md](m6-mcp.md) | MCP tools and the copy-the-action contract |
| [gcp-live-serving.md](gcp-live-serving.md) | How to stand up the live IAM-gated endpoint |
| [evidence/gcp-serving-run.md](evidence/gcp-serving-run.md) | A recorded live serving run |
| [d9-langsmith.md](d9-langsmith.md) | Optional LangSmith tracing |

## Platform and operations

| Doc | What it answers |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | End-to-end interview reference: stack, lifecycle, policy, ops |
| [simulation.md](simulation.md) | Holdout replay is the traffic contract |
| [monitoring.md](monitoring.md) | Dashboards, PSI, delayed labels |
| [m9-canary-replay.md](m9-canary-replay.md) | 90/10 canary and the bad-challenger proof |
| [m10-airflow.md](m10-airflow.md) | Job names as local CLIs (Composer off) |
| [m2-gcp-setup.md](m2-gcp-setup.md) · [m3-feast-setup.md](m3-feast-setup.md) · [m4-training-mlflow.md](m4-training-mlflow.md) | Milestone setup notes |
| [COST.md](../COST.md) | Budget, idle risk, teardown |
| [RUNBOOK.md](../RUNBOOK.md) | Day-of commands |
| [demo-script.md](demo-script.md) | Interview demo sequence |
| [repo-structure.md](repo-structure.md) | Target layout |

## Architecture decisions

| ADR | Decision |
|---|---|
| [0001](adr/0001-gcp-not-databricks.md) | GCP over Databricks Free Edition |
| [0002](adr/0002-feast-mlflow-airflow-vertex.md) | Split Feast / MLflow / Airflow / Vertex on purpose |
| [0003](adr/0003-demo-cost-switches.md) | Vertex Endpoint, Redis, Composer stay off |
| [0004](adr/0004-simulation-holdout-replay.md) | Chronological holdout replay instead of a live firehose |
| [0005](adr/0005-long-delivery-target.md) | Superseded hero (duration). Diagnostic only |
| [0006](adr/0006-handoff-promise-miss-noc.md) | Current hero: promise-miss at first scan + NOC policy |

## Build history

Milestone notes in [milestones.md](milestones.md). Spec deltas in [SPEC_AMENDMENTS.md](SPEC_AMENDMENTS.md). Follow-up ideas (not in scope) in [followup-decision-agentic-layer.md](followup-decision-agentic-layer.md).
