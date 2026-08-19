# First-scan OTIF

**Actionable ML in production shape:** a fulfillment problem, a model that drives an operating decision, and a measured outcome. Not a notebook. Not a dashboard.

This repo is the production loop on public [Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) Brazilian e-commerce data: seller, parcel, and delivery-promise events. A calibrated ranker is served on **GCP Cloud Run** (REST + MCP). A frozen exception policy turns the score into work. Agents execute that action; they do not invent a cheaper one.

It is a portfolio system you can run and inspect, not a live 3PL. Organic marketplace traffic is replaced by chronological holdout replay. The point is the path **raw data → production model → adopted decision**, with features, stack, architecture, and impact you can walk in a screen.

Walkthrough: [`ARCHITECTURE.md`](ARCHITECTURE.md) · Numbers: [`docs/business_assessment.md`](docs/business_assessment.md) · Product lock: [`docs/adr/0006-handoff-promise-miss-noc.md`](docs/adr/0006-handoff-promise-miss-noc.md)

---

## Screen answer: prod, features, stack, architecture, impact

### What is in production

Champion model **`local-20260818T041243Z`** (isotonic-calibrated XGBoost) scored in-process on Cloud Run `olist-ml-api` (IAM-gated, min instances 0). Same process mounts **REST** and **MCP** (`POST /mcp`). Local: `make serve-local` on `:8080`. Teardown: `make gcp-down`.

The **decision** in production is not “here is a probability.” It is a queue band: late notice, at-risk notice, remaining-leg upgrade proxy, or no action (`noc-handoff-policy-v1`). Promote, retrain, and spend above $20 stay with a person.

### Features

Knowable at **first carrier scan**. Historical windows are 7 / 30 / 90 day, events strictly before the scan, current order excluded. Train and serve share one contract.

| Group | Examples |
|---|---|
| Promise clocks | `handling_days`, `remaining_to_promise_days`, `handling_frac_of_promise`, `limit_miss` |
| Shipment | `item_count`, `basket_value`, `freight_value`, `geo_distance_km`, `same_state` |
| Seller history (Feast online) | `seller_order_count_{30,90}d`, `seller_late_rate_{30,90}d` |
| Context | purchase clocks, payment, customer/seller state |
| **Never in X** | customer delivery, raw carrier timestamp, reviews |

Detail below and in [`docs/features.md`](docs/features.md).

### Stack

**GCP · BigQuery · dbt · Feast · MLflow · XGBoost · FastAPI on Cloud Run · MCP.** Optional Vertex training pipeline; Vertex Endpoint / Redis / Composer stay off unless a person reviews cost. Terraform for IAM and teardown.

### Architecture

```text
Olist CSVs → (GCS) BigQuery → dbt marts → Feast
        → train / calibrate / register candidate (MLflow)
        → PredictionService (one object)
              ├─ REST  /v1/predict  /v1/decision  /v1/explain
              └─ MCP   predict_promise_miss  recommend_policy_action  …
        → frozen P0–P3 policy → agent copies action → simulated ledger
        → delayed-label eval, 90/10 canary, drift alarm, human promote
```

### Business impact (what is measured vs assumed)

**Measured:** ranking quality for an exception queue on a later test window (n = 14,471, **4.6%** miss rate). Top **2.5%** of scores: **41.6%** precision, **9.0×** lift vs random. Top **10%**: **22.2%** precision, **4.8×** lift, ~half of misses. Test PR-AUC **0.296**, ROC-AUC **0.816**, Brier **0.038**.

**Assumed, not causal:** miss cost, upgrade cost, and prevention rate (`econ-sim-v3`). `allow_causal_roi_claims: false`. Intervention lift needs an experiment (switchback or A/B on the action). This repo does not fake one. Ranking lift is the KPI this slice earned.

---

## The operating problem

Commerce here looks like a small fulfillment network: many sellers, a carrier handoff, a promised delivery date, and a customer who either gets the order on time or does not. At **first carrier scan** (`handoff_ts = order_delivered_carrier_date`) the seller is done. Remaining levers are the rest of the journey and customer communication.

```text
promise_miss = customer_delivery > order_estimated_delivery_date
```

| Clock | What it is | In the model? |
|---|---|---|
| `prediction_ts` | Approval (else purchase) | Handling / horizon only |
| `handoff_ts` | First carrier scan | Decision time, split key, point-in-time cutoff |
| Customer delivery | Label | **Never a feature** |

Duration (`delivery > 14 days`) was an earlier target. It ranks well (~0.53 PR-AUC) and answers the wrong question: most long orders were **promised** long. Promise-miss at approval was too weak (~0.10–0.22 PR-AUC) because the public ETA already absorbed geography and horizon. Scoring **at the scan** makes handling time, days left on the promise, and ship-limit miss legal — and is the delivery-promise problem.

This slice is **delivery prediction + exception management**, in that order: first a reliable promise-miss score, then a queue ops can run. Carrier routing would be a later model in the same portfolio, not this artifact.

The NYU definition this follows: **business problem → model that drives a decision → measurable outcome.** The decision is the exception band. The measured outcome is queue lift. Policy simulation informs spend conversation; it is not claimed P&L.

REST and MCP share `PredictionService`. Agents do not get a second, undocumented scorer.

---

## Model quality and queue lift

Champion **`local-20260818T041243Z`** (calibrated XGBoost, 8 Optuna trials). Test **n = 14,471**, promise-miss rate **4.6%**.

Lead with **exception-queue lift** (how much better the work list is than a random draw), then ranking/calibration. Accuracy on a rare miss is the wrong headline.

| Capacity (test) | Precision | Recall | Lift vs 4.6% base |
|---:|---:|---:|---:|
| Top 2.5% (P1-sized queue) | **41.6%** | 22.4% | **9.0×** |
| Top 10% (P2-sized queue) | **22.2%** | 48.0% | **4.8×** |

Among the highest-risk fortieth of later orders, about **2 in 5** actually miss the promise. The top tenth captures about **half** of test misses. That is the capacity story for a NOC: scarce attention, ranked work.

| Ranking / calibration | Test | Bootstrap 95% CI |
|---|---:|---|
| PR-AUC | **0.296** | 0.264 – 0.329 |
| ROC-AUC | **0.816** | 0.799 – 0.833 |
| Brier | 0.038 | 0.035 – 0.041 |
| ECE | 0.019 | — |

Validation (where policy cutoffs are frozen): PR-AUC **0.478**, ROC-AUC **0.838**. Test miss rate is lower than validation (12.3% → 4.6%). Thresholds stay frozen rather than being re-fit on later traffic, so the queue definition does not silently drift with the base rate.

Policy cutoffs from validation scores: **P1 = 0.5625**, **P2 = 0.3155**.

---

## Adopted workflow (policy) and governed agents

The model does not pick the action. A versioned policy (`noc-handoff-policy-v1`) is the contract ops and agents both consume — the analog of a governed metric: humans own the definition, tools query it.

| Band | Rule | Workflow action |
|---|---|---|
| **P0** | Remaining days to promise ≤ 0 | `LATE_NOTICE` (already late; clock rule, not a ranker) |
| **P1** | Score ≥ 0.5625 | `REMAINING_LEG_UPGRADE` if eligible, else `AT_RISK_NOTICE` |
| **P2** | Score ≥ 0.3155 | `AT_RISK_NOTICE` |
| **P3** | Else | `NO_ACTION` |

Upgrade eligibility (demo proxy, not a carrier SKU): P1 **and** `0 < remaining ≤ 7` days **and** (`geo ≥ 100 km` **or** not same state). Intervention cost ≥ **$20** waits for a person — high-stakes model-adjacent spend is not autonomous.

The agent **copies** `recommended_action`. Documented MCP tools are the skill surface (score, explain, recommend, simulate). The agent cannot substitute a cheaper eligible action. That is how agentic AI stays infrastructure: same APIs as the application, human-owned policy, human review on promote / retrain / spend.

### Unit economics in simulation — not claimed P&L

Versioned placeholders (`econ-sim-v3`) so a stakeholder conversation can happen in **cost per miss / cost per intervention**, not only PR-AUC:

```text
miss_cost     ≈ $10 + 10% of basket          (goodwill + value-at-risk stub)
upgrade_cost  ≈ freight-scaled placeholder   (clip $5–$80; not a carrier tariff)
notices       ≈ $1, 0% OTIF recovery in sim  (customer-impact only)
upgrade prevent rate ≈ 0.35                  (assumed Bernoulli, not fitted lift)
```

`allow_causal_roi_claims: false`. Ranking lift above is measured. **Intervention lift is not.** A self-serve experimentation / causal-inference platform is out of scope for this slice and would be the way to replace those assumptions. Real emails, tickets, and carrier APIs stay off (`real_external_execution_enabled: false`). Detail: [`docs/limitations-assumptions-proxies.md`](docs/limitations-assumptions-proxies.md).

---

## Features (messy ops data, leakage-safe)

Grain: one row per `order_id` at first scan. Historical windows are 7 / 30 / 90 day, events **strictly before** `handoff_ts`, current order excluded. Definitions live in dbt + a shared Python contract — the feature analog of a semantic layer: one meaning in train and in serve.

**Request-native (on `/v1/predict`):** basket, freight, item / seller / category counts, payment, customer and seller state, haversine distance, handling days, days remaining to promise, handling as a fraction of horizon, ship-limit miss, purchase clocks.

**Online Feast (seller only in v1):** `seller_order_count_{30,90}d`, `seller_late_rate_{30,90}d`. Stale lookup (>36h SLA) still predicts with priors and increments `stale_feature_rate`.

**Blocked:** reviews; raw carrier or customer delivery timestamps; any window that includes the current order.

Training and serving share [`src/olist_ml/features/contracts.py`](src/olist_ml/features/contracts.py). Feature audit: [`docs/features.md`](docs/features.md).

---

## Serving: REST and MCP

One FastAPI process so application traffic and agent traffic cannot diverge. Local: `make serve-local` → `http://127.0.0.1:8080`. Cloud: Cloud Run `olist-ml-api` on GCP (min instances 0, IAM invoker, not `allUsers`). MCP is Streamable HTTP at `POST /mcp` on the **same** URL.

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
| `POST` | `/v1/decision` | Predict → exception policy; optional simulate + ledger |
| `POST` | `/v1/action/simulate` | Execute a **named** action (no real side effects) |
| `GET` | `/v1/orders/{order_id}/decision` | Prediction / decision / action lineage |
| `GET` | `/v1/actions/{action_id}` | Ledger rows for one action |
| `POST` | `/v1/agent/review` | Copy-the-action review (optional human gate) |

### MCP tools (agent skill surface)

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

## Operating the model (notebook is not production)

There is no organic firehose. Traffic is a **deterministic chronological holdout** that never trains ([`docs/simulation.md`](docs/simulation.md)). Labels are not used for quality the day you score: a release job waits **seven days**, then delayed PR-AUC / Brier run on released rows only.

| Job | What it proves |
|---|---|
| Replay holdout | Same snapshot + seed → same request order |
| Label release | Quality jobs ignore truth until `prediction_ts + 7 days` |
| Delayed eval | PR-AUC / Brier on **released** rows only |
| Canary 90/10 | Stable `order_id` hash; `make canary-bad` should fail and recommend rollback |
| Drift | Feature PSI > 0.2 or high-band mix shift → **alarm**, not auto-retrain |
| Retrain | Person approval file; drift-reason also needs an active alarm |
| Promote | A later, separate person decision. Train CI does not deploy. Deploy CI does not train. |

Automation stops where adoption and money live: canary → 100% traffic, alarm → retrain, candidate → champion, `terraform apply`, real external side effects. That is high-stakes model review as an operating rule, not a slide.

---

## Stack

| Concern | Choice | Intentionally not |
|---|---|---|
| Cloud / warehouse | **GCP, BigQuery, dbt**, Terraform, teardown | A notebook with a warehouse screenshot |
| Features | Feast; **SQLite** online for this demo | Always-on Redis / Vertex Feature Store (cost) |
| Train / registry | Local **or Vertex pipeline**; **MLflow** is model truth | Notebook cells as the production path |
| Serve | FastAPI + joblib on **Cloud Run** | A second inference stack for agents |
| Orchestration | Airflow DAGs as local CLIs | Idle Cloud Composer |
| Agents | MCP tools + LangGraph **copy policy** | LLM chooses the exception band |

Vertex Endpoint, Memorystore Redis, and Composer stay **off** unless a person reviews a plan — same cost discipline you would want on a live GCP estate. Idle after `make gcp-down` is near $0/day. [`COST.md`](COST.md), [`docs/adr/0003-demo-cost-switches.md`](docs/adr/0003-demo-cost-switches.md).

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

- A live fulfillment network or carrier integration. Holdout replay substitutes for production traffic.
- An experimentation / causal-inference **platform**. Ranking lift is measured; intervention lift is assumed until an experiment exists.
- A causal ROI study or observed P&L. Simulated net value is not unit-economics proof.
- A full Decision Science portfolio. One production-shaped model: delivery promises and exception management — not routing, demand, or churn.
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
| `src/olist_ml/decisions/` | Exception policy, economics, routing |
| `src/olist_ml/agents/` | LangGraph copy-the-action graph |
| `src/olist_ml/actions/` | Simulated executor |
| `src/olist_ml/monitoring/` | Delayed labels, PSI, retrain approval |
| `dbt/` · `feature_repo/` · `pipelines/` · `airflow/dags/` · `terraform/` | Warehouse, features, train graph, jobs, IaC |
| `tests/` · `.github/workflows/` | Unit / API / model tests; CI does not auto-promote |

Interview order: [`ARCHITECTURE.md`](ARCHITECTURE.md) §17. Demo script: [`docs/demo-script.md`](docs/demo-script.md). Runbook: [`RUNBOOK.md`](RUNBOOK.md).

License: MIT. Data: [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) terms.
