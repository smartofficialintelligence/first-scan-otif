# First-scan OTIF

**Production-shaped ML for a fulfillment exception queue.**

At first carrier scan, score whether an order will miss the delivery date already promised to the customer. A frozen policy turns that score into work (notice, remaining-leg upgrade, or nothing). REST and MCP share one scorer. Agents copy the action. They cannot invent a cheaper one.

Public [Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) Brazilian e-commerce data. Runnable locally and on GCP. A portfolio system you can inspect, not a live 3PL.

```text
raw events → point-in-time features → calibrated ranker
                                         ↓
              measured queue lift  ←  frozen policy  ←  REST / MCP
                                         ↓
                              simulated action + ledger
```

The loop this is built to show: **business problem → model that drives a decision → measured outcome.**

| 60 seconds | 15 minutes | Deep dive |
|---|---|---|
| This page | [ARCHITECTURE.md](ARCHITECTURE.md) | [Documentation index](docs/README.md) |
| Skills and headlines below | Interview walk, §17 | Numbers, ADRs, runbooks, evidence |

---

## What this demonstrates

Hiring-manager scan. Each row is something you can open in the repo or watch in the screenshots.

| Skill | How it shows up here |
|---|---|
| **Decision-science framing** | Score is not the product. The product is a capacity-constrained exception queue with a versioned policy |
| **Leakage-safe features** | Decision time is first scan. Customer delivery is the label only. History is strictly before the scan. [features.md](docs/features.md) |
| **Train / serve contracts** | Shared column names in [`contracts.py`](src/olist_ml/features/contracts.py). Feast online lookup is **on** in the Cloud Run request path after a pandas/warehouse PIT parity fix |
| **Ranking + calibration** | XGBoost + Optuna + isotonic. Lead with queue lift, not accuracy. PR-AUC / Brier / ECE reported |
| **Human-gated MLOps** | MLflow candidate → named promote. Canary, delayed labels, drift alarm. Train CI does not deploy |
| **Governed agents** | MCP + LangGraph **copy** `recommended_action`. Server refuses any other named execute |
| **Production serving** | FastAPI on Cloud Run (IAM, min instances 0). REST and MCP are one `PredictionService` |
| **Warehouse + IaC** | BigQuery, dbt, Terraform, teardown. Vertex Endpoint / Redis / Composer stay off for cost |

**Stack:** GCP · BigQuery · dbt · Feast · MLflow · XGBoost · FastAPI / Cloud Run · MCP · LangGraph · Airflow-as-CLI · Terraform

---

## Headlines (later test window)

Champion `local-20260821T203846Z`. Test **n = 14,471**, miss rate **4.6%**.

| | |
|---|---|
| Top **2.5%** of scores (P1-sized queue) | **46.0%** precision, **10.0×** lift vs random |
| Top **10%** (P2-sized queue) | **22.5%** precision, **4.9×** lift, ~half of all misses |
| Ranking / calibration | PR-AUC **0.310**, ROC-AUC **0.827**, Brier **0.037**, ECE **0.004** |
| Live serve (2k replay) | 100% HTTP 200, **p95 162 ms**, scale-to-zero after |

**Measured:** ranking quality for an exception queue. **Assumed, not causal:** miss cost, upgrade cost, prevention rate. `allow_causal_roi_claims: false`. Full tables: [business_assessment.md](docs/business_assessment.md). Current-champion holdout snapshot (9,647 orders, 603 interventions, 25 late→on-time under sim): [decision-impact-holdout-local-20260821T203846Z.md](docs/evidence/decision-impact-holdout-local-20260821T203846Z.md).

---

## The operating problem

Seller work is done at first carrier scan (`handoff_ts = order_delivered_carrier_date`). Remaining levers are the rest of the journey and customer communication.

```text
promise_miss = customer_delivery > order_estimated_delivery_date
```

Duration (“will this take more than 14 days?”) ranks well and answers the wrong question: most long orders were already *promised* long. Promise-miss *at approval* is too weak because the public ETA already absorbed geography. Scoring **at the scan** makes handling time, days left on the promise, and ship-limit miss legal.

| Band | Rule | Action |
|---|---|---|
| **P0** | Remaining days ≤ 0 | `LATE_NOTICE` (clock rule, not the ranker) |
| **P1** | Score ≥ 0.4895 | Remaining-leg upgrade if eligible, else at-risk notice |
| **P2** | Score ≥ 0.2387 | `AT_RISK_NOTICE` |
| **P3** | Else | `NO_ACTION` |

Spend ≥ **$20** waits for a person. Cutoffs travel in `model_meta.json`, so a promote can move them. Why this label and these bands: [ADR 0006](docs/adr/0006-handoff-promise-miss-noc.md).

---

## See it running

A coding agent on the **live IAM-gated Cloud Run** MCP endpoint. Same `PredictionService` as REST. No side channel.

<details>
<summary><strong>1 · What's serving</strong>: champion version and frozen P1/P2 cutoffs from the promoted artifact</summary>

![Agent calls get_model_status: champion version, cutoffs, ranking and calibration](docs/img/01-mcp-model-status.png)

</details>

<details>
<summary><strong>2 · Score → banded action</strong>: P1 upgrade, human approval required because spend is above $20</summary>

![Agent calls recommend_policy_action: P1 band, upgrade action, human approval required](docs/img/02-decision-p1-upgrade.png)

</details>

<details>
<summary><strong>3 · Why this order</strong>: Tree SHAP. Remaining promise days and handling fraction, not basket size</summary>

![Agent calls explain_promise_miss: top risk drivers](docs/img/03-shap-risk-drivers.png)

</details>

<details>
<summary><strong>4 · Simulated execution can fail</strong>: this draw did not prevent the miss. Net is negative and the seed is recorded</summary>

![Simulated execution: intervention failed this draw, net negative, seed recorded](docs/img/04-simulated-execution.png)

</details>

<details>
<summary><strong>5 · The agent cannot pick a cheaper action</strong>: server refuses any execute that is not the frozen policy action</summary>

![Server refuses AT_RISK_NOTICE: not the frozen policy action for this decision](docs/img/05-policy-refusal.png)

</details>

<details>
<summary><strong>6 · Lineage</strong>: prediction → decision → action → outcome, one append-only chain per order</summary>

![Decision ledger lineage for the order](docs/img/06-decision-lineage.png)

</details>

<details>
<summary><strong>7 · Live platform telemetry</strong>: 2,000-request replay, p95 162 ms, scale-to-zero billable time</summary>

![Cloud Monitoring: request plateau, p95 latency, scale-to-zero billable time](docs/img/07-cloud-monitoring.png)

The ~1-minute lines in the latency tile are held-open **agent MCP streaming connections**, not inference latency.

</details>

---

## Architecture (one picture)

```text
Olist CSVs → GCS → BigQuery → dbt marts ─┐
                                         ├→ Feast (offline: BQ, online: SQLite)
Olist CSVs → pandas PIT feature table ───┘
        → train / calibrate → MLflow candidate → human promote → champion joblib
        → PredictionService (request + Feast online → baked joblib)
              ├─ REST  /v1/predict  /v1/decision  /v1/explain
              └─ MCP   predict_promise_miss  recommend_policy_action  …
        → frozen P0–P3 policy → LangGraph copies action → simulated ledger
        → delayed-label eval, 90/10 canary, drift alarm, human promote
```

Seams, tradeoffs, and the “why not one vendor lifecycle” story: [ARCHITECTURE.md](ARCHITECTURE.md). Cost switches: [COST.md](COST.md).

---

## Run it

Python **3.12+**. [`uv`](https://docs.astral.sh/uv/) recommended. Day-of sequence: [RUNBOOK.md](RUNBOOK.md). Interview recording: [demo-script.md](docs/demo-script.md).

```bash
make sync
make fixtures              # or: make download-olist
make test
make serve-local           # REST + MCP on :8080
make demo-decision         # P0–P3 + ledger (no LLM required)
make decision-eval         # action mix / late→on-time / spend (simulated)

# live GCP (IAM-gated; tear down after)
make gcp-up && make gcp-smoke && make gcp-down
```

`make train-pipeline` writes a **candidate**, never the champion. Promote is a named human step: `make promote-candidate APPROVED_BY=<you>`.

---

## What this is not

- A live fulfillment network or carrier integration. Holdout replay substitutes for production traffic.
- A causal ROI study or observed P&L. Ranking lift is measured. Intervention lift is assumed until an experiment exists.
- An LLM operations bot. No model chooses P0–P3.
- A full decision-science portfolio. One production-shaped slice: delivery promises and exception management.

License: MIT. Data: [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) terms.
