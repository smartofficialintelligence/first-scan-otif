# Locked Decisions

Status: **binding for implementation** unless superseded by a new ADR.  
Date locked: 2026-08-15  
Supersedes technology choices in the draft Cursor spec v0.2 where they conflict.

---

## 1. Platform

| Decision | Locked value |
|---|---|
| Cloud | GCP |
| Not using | Databricks (including Free Edition) for this artifact |
| Primary region | `us-central1` |
| IaC | Terraform |
| CI/CD | GitHub Actions |
| Package/runtime | Python 3.12, `uv`, Docker, Artifact Registry |

Rationale: portfolio demonstrates transferable open ML platform seams on real cloud infra (IAM, Terraform, tear-down). See [ADR 0001](adr/0001-gcp-not-databricks.md).

---

## 2. Component ownership (revised stack)

| Concern | Owner |
|---|---|
| Warehouse | BigQuery |
| Feature engineering | dbt Core + dbt-bigquery |
| Feature registry + offline/online serving | Feast (offline: BigQuery; online: Memorystore Redis, demo-only) |
| Cross-system orchestration, schedules, drift/retrain triggers | Airflow (ephemeral/local for day-to-day; Composer only for live demos) |
| ML training workflow | Vertex AI Pipelines |
| Experiments + model registry | MLflow (Cloud Run + GCS artifact store; optional Cloud SQL if needed) |
| Online model inference | Vertex AI Endpoint (champion/challenger traffic split) |
| Consumer interfaces | FastAPI on Cloud Run — REST + MCP over one `PredictionService` |

See [ARCHITECTURE.md](../ARCHITECTURE.md) and [ADR 0002](adr/0002-feast-mlflow-airflow-vertex.md).

---

## 3. ML problem (Human gate H1 — locked defaults)

| Decision | Locked value |
|---|---|
| Entity | Olist order (`order_id`) |
| Prediction moment | `order_approved_at` (fallback: `order_purchase_timestamp` if approval null) |
| Target | `long_delivery = (order_delivered_customer_date - prediction_ts) > 14 days` (H1 amended; see [ADR 0005](adr/0005-long-delivery-target.md)) |
| Output | `P(long_delivery)` calibrated probability + risk band |
| Exclude | Orders missing delivery date, estimated delivery date, or prediction timestamp; cancelled / non-delivered where target undefined |
| Unavailable at prediction time | All post-approval logistics timestamps, carrier events, review scores, post-purchase status changes, anything after prediction timestamp |
| Primary metric | PR-AUC |
| Secondary metrics | ROC-AUC, Brier, calibration error (ECE), precision/recall at capacity thresholds, segment metrics |
| Production metrics | Latency, error rate, volume, feature freshness/drift, prediction drift, delayed-label quality |

Details: [ml-problem.md](ml-problem.md).

---

## 4. Modeling patterns (from seed notebook — adapted)

| Pattern | Locked approach |
|---|---|
| Model | XGBoost classifier |
| HPO | Optuna, maximize PR-AUC; modest trial budget in demo (`n_trials` default 25) |
| Class imbalance | `scale_pos_weight` (or equivalent); **no SMOTE** on the production path (calibration-friendly) |
| Calibration | Isotonic via `CalibratedClassifierCV` (or equivalent held-out isotonic) |
| Validation | Temporal train / validation / test — no random shuffle across time |
| Eval extras | Bootstrap CIs, threshold/capacity tables, SHAP + permutation importance, segmented evaluation |
| Leakage | Point-in-time features only; automated checks where practical |

Seed workbook is conceptual only (DoorDash domain). Do not port notebook structure or private schema.

---

## 5. Features

| Decision | Locked value |
|---|---|
| Feature definitions | dbt marts only — no train-only transforms that serving cannot reproduce |
| Online subset | Seller-level historical features via Feast (see [features.md](features.md)) |
| Historical windows | `7d`, `30d`, `90d` rolling, `closed` strictly before prediction timestamp |
| Distance proxy | Haversine customer↔seller from geolocation aggregates known at prediction time |
| Human gate H2 | Required before treating feature set as production-approved |

Full candidate list + leakage flags: [features.md](features.md).

---

## 6. Data & traffic simulation

| Decision | Locked value |
|---|---|
| Source data | Public Olist only — no synthetic customers/orders for the core dataset |
| Splits | Chronological: train / validation / test / **replay holdout** |
| Traffic | Deterministic replay of holdout through FastAPI (`scripts/replay_traffic.py`) |
| Canary split | 90% champion / 10% challenger on Vertex Endpoint |
| Label availability | Simulated delay then join (default 7 days after prediction timestamp for demo logic) |
| Drift | Controlled feature shifts on a named scenario set — not random noise |
| Bad canary | Intentionally degraded model artifact |

Contract: [simulation.md](simulation.md).

---

## 7. Cost & demo switches

| Decision | Locked value |
|---|---|
| Hard planning budget | $75 |
| Target first MVP demo | ≤ $30 |
| Expected demo/dev band | ~$20–$60 |
| Idle goal | **Near $0/day** after `make demo-down` |
| Canonical data at rest when off | GCS (and/or gitignored local raw); BQ datasets deleted or emptied on down |
| Always-on forbidden when idle | Vertex Endpoint, Memorystore, Composer, Cloud Run min instances > 0 |

Details: [COST.md](../COST.md), [ADR 0003](adr/0003-demo-cost-switches.md).

---

## 8. Serving & interfaces

| Decision | Locked value |
|---|---|
| REST | `GET /health`, `GET /ready`, `GET /v1/model`, `POST /v1/predict`, `POST /v1/explain`, plus decision/agent: `/v1/decision`, `/v1/action/simulate`, `/v1/actions/{action_id}`, `/v1/policies/current`, `/v1/orders/{id}/decision`, `/v1/agent/review`, `/v1/metrics` |
| MCP tools | `predict_long_delivery`, `explain_long_delivery`, `get_model_status`, `get_model_metrics`, plus D7 decision tools (`recommend_policy_action`, `execute_simulated_action`, …) — see [m6-mcp.md](m6-mcp.md) |
| Agent review | LangGraph tool-driven workflow (`olist_ml.agents`); optional human gate; optional LangSmith ([d9-langsmith.md](d9-langsmith.md)); install `uv sync --extra agent` |
| Shared path | REST and MCP → `PredictionService` → Feast online (when on) + Vertex Endpoint |
| Auth (demo) | API key required when `AUTH_MODE=api_key`; open only for local dev |
| Explain | SHAP on sampled/synchronous path behind `/v1/explain` with latency guardrails (timeout/budget) |

---

## 9. Model lifecycle states

Logical states (MLflow tags/aliases):

```text
TRAINED → EVALUATED → REGISTERED_CANDIDATE → APPROVED_FOR_CANARY
  → CANARY → CHAMPION → SUPERSEDED
                ↘ ROLLED_BACK
```

No automatic promotion past human gates H3/H4/H6.

---

## 10. Human gates (unchanged intent)

| Gate | Topic |
|---|---|
| H1 | Problem / prediction time / metrics — **locked in this doc** |
| H2 | Feature / leakage audit — **done for portfolio v1** ([h2-feature-audit.md](h2-feature-audit.md)) |
| H3 | Offline candidate evaluation |
| H4 | Canary → full production |
| H5 | Monitoring-triggered retrain decision |
| H6 | Retrained candidate approval |
| H7 | Terraform apply / IAM |
| H8 | Rollback / exceptional ops |
| H9 | Business-loss economics — **approved as simulation defaults** ([h9-h10-economics-gate.md](h9-h10-economics-gate.md)) |
| H10 | Intervention effectiveness — **approved as simulation defaults** (same doc) |
| H11 | Agent action scope / mandatory human review thresholds — defaults locked in policy YAML |
| H12 | Real external execution — **forbidden** (`real_external_execution_enabled: false`) |

---

## 11. Gate numerics

Initial configurable defaults are locked in [gate-defaults.md](gate-defaults.md).  
Re-tune from evidence; do not bikeshed before first metrics.

---

## 12. Explicitly deferred (do not bikeshed now)

- Whether MLflow needs Cloud SQL vs file/GCS-backed store for v1 (default: Cloud Run + GCS artifacts; add DB only if required)
- Composer vs Astronomer vs local Airflow for the *first* orchestration milestone (interface = DAGs; hosting chosen at Milestone 10; Composer never left idle)
- Final public GitHub visibility / branding copy

---

## 13. Build order (milestones)

1. Local production model + FastAPI  
2. BigQuery + dbt  
3. Feast  
4. Vertex training pipeline + MLflow  
5. Vertex Endpoint + Cloud Run serving  
6. MCP  
7. CI/CD + Terraform hardening  
8. Monitoring  
9. Canary + replay + rollback (**simulation contract required**)  
10. Airflow schedule/drift/retrain triggers  
11. Polish, COST.md actuals, demo script  

Milestone 1 does **not** include GCP, dbt, Feast, MCP, or Airflow.
