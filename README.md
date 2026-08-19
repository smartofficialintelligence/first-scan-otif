# First-scan OTIF

**Score a parcel at the first carrier scan. Put it on a frozen exception queue. Let an agent execute that action — not invent a cheaper one. Measure ranking quality and simulated impact without claiming causal ROI.**

This repo is a production-shaped decision-science system on public [Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) Brazilian e-commerce orders. It is a portfolio artifact, not a live carrier product. The goal is to show the full loop a fulfillment NOC actually needs: leakage-safe features, a calibrated ranker, a deterministic policy, dual serving (REST + MCP), delayed-label operations, and honest economics.

Walkthrough: [`ARCHITECTURE.md`](ARCHITECTURE.md) · Business numbers: [`docs/business_assessment.md`](docs/business_assessment.md) · Locked product: [`docs/adr/0006-handoff-promise-miss-noc.md`](docs/adr/0006-handoff-promise-miss-noc.md)

---

## Why this exists

Most “ML demos” stop at a notebook metric. Production decision science starts after the score:

1. **The right question at the right clock.** Not “will this take a long time?” — that mostly reconstructs the public ETA. The question is: *will we miss the promise we already made?*
2. **A model that ranks work for a capacity-constrained queue.** Precision at the top of the list matters more than accuracy on a 4.6% event.
3. **A frozen policy the business can explain.** Bands are rules, not `argmax` expected value.
4. **An agent that copies policy.** Tools can score, explain, and execute. They cannot shop for a cheaper action.
5. **Measurement with a disclaimer.** Intervention dollars are versioned simulation assumptions. `allow_causal_roi_claims: false`.

That chain — **predict → decide → execute → ledger → delayed eval** — is the artifact.

---

## The operational job

At **first carrier scan** (`handoff_ts = order_delivered_carrier_date`) the seller is done. The remaining lever is the rest of the journey plus customer communication.

```text
promise_miss = customer_delivery > order_estimated_delivery_date
```

| Clock | What it is | Allowed as a feature? |
|---|---|---|
| `prediction_ts` | Approval (else purchase) | Handling / horizon only |
| `handoff_ts` | First carrier scan | Decision time, split key, PIT cutoff |
| Customer delivery | Label | **Never in X** |

Duration (`delivery > 14 days`) was an earlier hero target. It is a stronger ranker (~0.53 PR-AUC) and a worse product: most long orders were **promised** long. Promise-miss at approval was too weak (~0.10–0.22 PR-AUC) because the public ETA already ate geo and horizon. Scoring **at the scan** makes handling time, days left on the promise, and ship-limit miss legal — and is the OTIF question.

---

## What ships

```text
public Olist CSVs
        │
        ▼
  dbt marts (labels, point-in-time history, geo)
        │
        ▼
  Feast  ── offline train  /  SQLite online seller lookup
        │
        ▼
  Calibrated XGBoost  (Optuna on PR-AUC → isotonic on frozen valid)
        │
        ▼
  PredictionService     ←── one object for REST, MCP, replay, training
        │
        ▼
  noc-handoff-policy-v1   P0–P3 bands, frozen validation thresholds
        │
        ▼
  LangGraph agent copies recommended_action
        │
        ▼
  Simulated ActionExecutor → JSONL ledger
        │
        ▼
  Operate: holdout replay → 7-day label release → delayed PR-AUC
           canary 90/10 → PSI drift alarms → human-gated retrain/promote
```

REST and MCP share `PredictionService`. There is no second scorer for agents.

---

## Model quality

Champion **`local-20260818T041243Z`** (calibrated XGBoost, 8 Optuna trials). Test **n = 14,471**, miss rate **4.6%**.

| Metric | Test | Bootstrap 95% CI |
|---|---:|---|
| PR-AUC | **0.296** | 0.264 – 0.329 |
| ROC-AUC | **0.816** | 0.799 – 0.833 |
| Brier | 0.038 | 0.035 – 0.041 |
| ECE | 0.019 | — |

Validation (where policy cutoffs are frozen): PR-AUC **0.478**, ROC-AUC **0.838**. Test miss rate is lower than validation (12.3% → 4.6%). That temporal shift is part of the story; thresholds stay frozen rather than being re-fit on later traffic.

### Queue capacity (the number a NOC uses)

Flag by predicted risk vs the **test** base rate of 4.6%. Policy bands use **validation score** cutoffs, not these test percentiles.

| Capacity | Precision | Recall | Lift vs 4.6% |
|---:|---:|---:|---:|
| Top 2.5% (P1-sized) | **41.6%** | 22.4% | **9.0×** |
| Top 10% (P2-sized) | **22.2%** | 48.0% | **4.8×** |

Among the highest-risk fortieth of later orders, about **2 in 5** actually miss the promise. The top tenth captures about **half** of test misses.

Frozen policy cutoffs from validation scores: **P1 = 0.5625**, **P2 = 0.3155**.

Accuracy is the wrong headline on a rare event. Ranking + calibration + a capacity story is the product.

---

## Policy and the agent

The model does not pick an action. `noc-handoff-policy-v1` maps score + clocks to a band:

| Band | Rule | Action |
|---|---|---|
| **P0** | Remaining days to promise ≤ 0 | `LATE_NOTICE` (clock rule, not a ranker) |
| **P1** | Score ≥ 0.5625 | `REMAINING_LEG_UPGRADE` if eligible, else `AT_RISK_NOTICE` |
| **P2** | Score ≥ 0.3155 | `AT_RISK_NOTICE` |
| **P3** | Else | `NO_ACTION` |

Upgrade eligibility (demo proxy, not a carrier SKU): P1 **and** `0 < remaining ≤ 7` days **and** (`geo ≥ 100 km` **or** not same state). Spend ≥ **$20** waits for a person.

The LangGraph agent **copies** `recommended_action`. It does not re-rank EV or substitute a cheaper eligible action. That is a product rule, not a prompt suggestion: tools expose the catalog; execution takes the frozen action.

### Simulated economics (`econ-sim-v3`) — not P&L

```text
miss_cost     ≈ $10 + 10% of basket
upgrade_cost  ≈ freight-scaled lognormal placeholder (clip $5–$80)
notices       ≈ $1, 0% OTIF recovery in sim (customer-impact only)
upgrade prevent rate ≈ 0.35 Bernoulli assumption
```

`allow_causal_roi_claims: false`. Real emails, tickets, and carrier APIs are off (`real_external_execution_enabled: false`). Detail: [`docs/limitations-assumptions-proxies.md`](docs/limitations-assumptions-proxies.md).

---

## Features

Grain: one row per `order_id` at first scan. Historical windows are 7 / 30 / 90 day, events **strictly before** `handoff_ts`, current order excluded.

**Request-native (on `/v1/predict`):** basket, freight, item / seller / category counts, payment, customer and seller state, haversine distance, handling days, days remaining to promise, handling as a fraction of horizon, ship-limit miss, purchase clocks.

**Online Feast (seller only in v1):** `seller_order_count_{30,90}d`, `seller_late_rate_{30,90}d`. Stale lookup (>36h SLA) still predicts with priors and increments `stale_feature_rate`.

**Blocked:** reviews; raw carrier or customer delivery timestamps; any window that includes the current order.

Training and serving share [`src/olist_ml/features/contracts.py`](src/olist_ml/features/contracts.py). Feature audit: [`docs/features.md`](docs/features.md).

---

## Serving: REST and MCP

One FastAPI process. Local: `make serve-local` → `http://127.0.0.1:8080`. Cloud: Cloud Run `olist-ml-api` (min instances 0, IAM invoker, not `allUsers`). MCP is Streamable HTTP at `POST /mcp` on the **same** URL.

### REST

| Method | Path | Role |
|---|---|---|
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Artifact loaded + `model_version` |
| `GET` | `/v1/model` | Metrics, P1/P2 thresholds |
| `GET` | `/v1/metrics` | In-process serving counters |
| `POST` | `/v1/predict` | `promise_miss_probability`, `risk_band`, ids |
| `POST` | `/v1/explain` | Tree SHAP on the booster (pre-calibration; displayed `p` is isotonic) |
| `GET` | `/v1/policies/current` | Frozen policy + simulation economics |
| `POST` | `/v1/decision` | Predict → NOC policy; optional simulate + ledger |
| `POST` | `/v1/action/simulate` | Execute a **named** action (no real side effects) |
| `GET` | `/v1/orders/{order_id}/decision` | Prediction / decision / action lineage |
| `GET` | `/v1/actions/{action_id}` | Ledger rows for one action |
| `POST` | `/v1/agent/review` | LangGraph copy-the-action review (optional human gate) |

### MCP tools

Same domain services as REST. No duplicated inference.

| Tool | Maps to |
|---|---|
| `predict_promise_miss` / `get_order_risk` | `PredictionService.predict_one` |
| `explain_promise_miss` | `PredictionService.explain_one` |
| `get_model_status` / `get_model_metrics` | readiness + `model_info` |
| `recommend_policy_action` | predict → `DecisionService` (`POST /v1/decision`) |
| `list_available_actions` / `get_policy_metrics` | `noc-handoff-policy-v1` + `econ-sim-v3` |
| `calculate_action_value` | simulation score for one approved action |
| `execute_simulated_action` | `ActionExecutor` (ledger only) |
| `get_decision_history` / `get_action_outcome` | lineage by `order_id` / `action_id` |

Cursor (IAM identity token, ~1h TTL — do not commit it):

```json
{
  "mcpServers": {
    "olist-ml": {
      "url": "https://<cloud-run-host>/mcp",
      "headers": {
        "Authorization": "Bearer <gcloud auth print-identity-token>"
      }
    }
  }
}
```

Local stdio: `make mcp-serve`. After `gcp-up`, resolve the URI with `gcloud run services describe olist-ml-api --region=us-central1 --format='value(status.url)'`.

---

## Operating the model

There is no organic firehose. Traffic is a **deterministic chronological holdout** that never trains ([`docs/simulation.md`](docs/simulation.md)).

| Job | What it proves |
|---|---|
| Replay holdout | Same snapshot + seed → same request order |
| Label release | Quality jobs ignore truth until `prediction_ts + 7 days` |
| Delayed eval | PR-AUC / Brier on **released** rows only |
| Canary 90/10 | Stable `order_id` hash; `make canary-bad` is supposed to fail and recommend rollback |
| Drift | Feature PSI > 0.2 or high-band mix shift → **alarm**, not auto-retrain |
| Retrain | Person approval file; drift-reason also needs an active alarm |
| Promote | A later, separate person decision. Train CI does not deploy. Deploy CI does not train. |

Automation stops at risk-bearing steps: canary → 100%, alarm → retrain, candidate → champion, `terraform apply`, real external side effects.

---

## Stack (and what was left off)

| Concern | Choice | Intentionally not |
|---|---|---|
| Cloud | GCP, Terraform, teardown | Databricks-as-the-whole-product |
| Warehouse / transforms | BigQuery + dbt | Train-only pandas as source of truth |
| Features | Feast; **SQLite** online | Always-on Redis / Vertex Feature Store for this demo |
| Train / registry | Local or Vertex pipeline; **MLflow** is model truth | Notebook cells as production |
| Serve | FastAPI + joblib on Cloud Run | Separate inference stacks per interface |
| Orchestration | Airflow DAGs as local CLIs | Idle Cloud Composer |
| Agent | LangGraph copies policy | LLM chooses the band |

Vertex Endpoint, Memorystore Redis, and Composer stay **off** unless a person reviews a plan. Idle after `make gcp-down` is near $0/day. Cost intent: [`COST.md`](COST.md), [`docs/adr/0003-demo-cost-switches.md`](docs/adr/0003-demo-cost-switches.md).

---

## Run it

Python **3.12+**. [`uv`](https://docs.astral.sh/uv/) recommended.

```bash
make sync
make fixtures              # or: make download-olist  (full public CSVs)
make test
make serve-local           # REST + MCP on :8080
make smoke-local
make demo-decision         # P0–P3 + ledger, no LLM required for policy copy
make canary-bad            # degraded challenger should fail delayed-label gate

# live GCP (IAM-gated; tear down after the demo)
make gcp-up && make gcp-smoke && make gcp-down
```

Lint: `make lint`. Full local train: `make train-pipeline` (registers a **candidate**, not champion).

---

## What this is not

- A live marketplace or carrier integration. Holdout replay substitutes for production traffic.
- A causal ROI study. Simulated net value is not observed P&L.
- An LLM operations bot. No model chooses P0–P3.
- A production SLO. Feast online is SQLite; SHAP is tree-level; freshness is logged even when Feast is off.

---

## Code map

| Path | Role |
|---|---|
| `src/olist_ml/features/` | Contracts, assembler, Feast, handoff clocks |
| `src/olist_ml/training/` | Tune, train, calibrate, evaluate, offline gates |
| `src/olist_ml/inference/` | `PredictionService` |
| `src/olist_ml/api/` | FastAPI + MCP |
| `src/olist_ml/decisions/` | NOC policy, economics, routing |
| `src/olist_ml/agents/` | LangGraph copy-the-action graph |
| `src/olist_ml/actions/` | Simulated executor |
| `src/olist_ml/monitoring/` | Delayed labels, PSI, retrain approval |
| `dbt/` · `feature_repo/` · `pipelines/` · `airflow/dags/` · `terraform/` | Warehouse, features, train graph, jobs, IaC |
| `tests/` · `.github/workflows/` | Unit / API / model tests; CI does not auto-promote |

Interview order: [`ARCHITECTURE.md`](ARCHITECTURE.md) §17. Demo script: [`docs/demo-script.md`](docs/demo-script.md). Runbook: [`RUNBOOK.md`](RUNBOOK.md).

License: MIT. Data: [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) terms.
