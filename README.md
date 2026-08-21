# First-scan OTIF

**Actionable ML in production shape:** a fulfillment problem, a model that drives an operating decision, and a measured outcome. 

This repo is the production loop on public [Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) Brazilian e-commerce data: seller, parcel, and delivery-promise events. A calibrated ranker is served on **GCP Cloud Run** (REST + MCP). A frozen exception policy turns the score into work. LangGraph copies that action; MCP `execute_simulated_action` and REST `/v1/action/simulate` reject any other named action.

It is a portfolio system you can run and inspect, not a live 3PL. Organic marketplace traffic is replaced by chronological holdout replay. The point is the path **raw data → production model → adopted decision**, with features, stack, architecture, and impact you can walk in a screen.

Walkthrough: [`ARCHITECTURE.md`](ARCHITECTURE.md) · Numbers: [`docs/business_assessment.md`](docs/business_assessment.md) · Product lock: [`docs/adr/0006-handoff-promise-miss-noc.md`](docs/adr/0006-handoff-promise-miss-noc.md)

---

## Screen answer: prod, features, stack, architecture, impact

### What is in production

Champion model **`local-20260819T170145Z`** (isotonic-calibrated XGBoost) scored in-process on Cloud Run `olist-ml-api` (IAM-gated, min instances 0). Same process mounts **REST** and **MCP** (`POST /mcp`). Local: `make serve-local` on `:8080`. Teardown: `make gcp-down`.

The **decision** in production is not “here is a probability.” It is a queue band: late notice, at-risk notice, remaining-leg upgrade proxy, or no action (`noc-handoff-policy-v1`). Promote, retrain, and spend above $20 stay with a person.

### Features

Knowable at **first carrier scan**. Historical windows are 7 / 30 / 90 day; prior **handoffs** are strictly before the scan; current order excluded. Train and serve share column names in [`contracts.py`](src/olist_ml/features/contracts.py). Omitted online seller history can be filled from **Feast** (the Cloud Run image ships the Feast client, the serving config, and the materialized SQLite store); remaining missing history is 0 after that lookup. Hydration is **on**: the pandas builder and the dbt/Feast warehouse now agree exactly on all six online seller features across 96,475 rows. Reaching that took a fix on each side — a tie-handling bug in the pandas point-in-time windows and hour-truncation in the dbt label. See [ARCHITECTURE.md §6](ARCHITECTURE.md). Lookups fail open — an unmaterialized store degrades to cold-start defaults instead of erroring, and trips a circuit breaker so no request pays registry-load latency twice.

| Group | Examples |
|---|---|
| Promise clocks | `handling_days`, `remaining_to_promise_days`, `handling_frac_of_promise`, `limit_miss` |
| Shipment | `item_count`, `basket_value`, `freight_value`, `geo_distance_km`, `same_state` |
| Seller history (request fields) | `seller_order_count_{7,30,90}d`, `seller_late_rate_{7,30,90}d` |
| Context | purchase clocks, payment, customer/seller state |
| **Never in X** | customer delivery, raw carrier timestamp, reviews |

Detail below and in [`docs/features.md`](docs/features.md).

### Stack

**GCP · BigQuery · dbt · Feast · MLflow · XGBoost · FastAPI on Cloud Run · MCP.**  <br>
**Optimized for cost:** Turn-key Terraform deployment and teardown of assets and IAM governance.
Vertex Endpoint / Redis / Composer are disabled; the Vertex pipeline file is a **compile-or-skip stub**, not a second training path.

### Architecture

```text
Olist CSVs → GCS raw bucket → BigQuery → dbt marts ─┐
                                                    ├→ Feast (offline: BQ, online: SQLite)
Olist CSVs → pandas PIT feature table ──────────────┘   warehouse snapshot / Feast history
        → train / calibrate → MLflow candidate → human promote → champion joblib
        → PredictionService (request + Feast online lookup → baked joblib)
              ├─ REST  /v1/predict  /v1/decision  /v1/explain
              └─ MCP   predict_promise_miss  recommend_policy_action  …
        → frozen P0–P3 policy → LangGraph copies action → simulated ledger
        → delayed-label eval, 90/10 canary, drift alarm, human promote
```

### Business impact (what is measured vs assumed)

**Measured:** ranking quality for an exception queue on a later test window (n = 14,471, **4.6%** miss rate). Top **2.5%** of scores: **46.0%** precision, **10.0×** lift vs random. Top **10%**: **22.5%** precision, **4.9×** lift, ~half of misses. Test PR-AUC **0.310**, ROC-AUC **0.827**, Brier **0.037**.

**Assumed, not causal:** miss cost, upgrade cost, and prevention rate (`econ-sim-v3`). Replay also credits **delay days avoided** when an upgrade Bernoulli succeeds (observed overrun, or a 6-day miss median). Notices do not change days late. No new EDD is invented. `allow_causal_roi_claims: false`. Intervention lift needs an experiment (switchback or A/B on the action). This repo does not fake one. Ranking lift is the KPI this slice earned.

**Simulated ops rollup (same assumptions, operator language):** `make demo-decision` appends NOC simulations to the ledger; holdout `scripts/policy_replay.py` does the same at window scale. Then `make decision-eval` prints and writes `artifacts/decision_impact.md` — how many of each action ran, how many deliveries moved late→on-time, delay-days avoided, and spend. Same block is `business_sim` on `GET /v1/metrics` and in `make export-monitoring`. If the ledger has no actions, eval falls back to `artifacts/policy_replay_report.json`. That is the JD-facing outcome sentence. It is still not observed P&L. A full-holdout snapshot (9,647 orders): [`docs/evidence/decision-impact-holdout.md`](docs/evidence/decision-impact-holdout.md) — 630 interventions, 27 late deliveries moved on-time, 88.8 delay-days avoided, $1,432 simulated spend — including a three-policy comparison (do-nothing / naive threshold / NOC) where the cheap-notice baseline "wins" on simulated net value while changing zero physical outcomes. That asymmetry is why the policy is a banded capacity rule, not EV-argmax, and why intervention lift waits for an experiment.

---

## See it running — an agent on the governed tool surface

A coding agent (Cursor) connected to the **live IAM-gated Cloud Run endpoint** over MCP — same `PredictionService` the REST API uses, no side channel. Model → frozen policy → simulated action → refusal when an agent tries to substitute.

**1 · What's serving.** `get_model_status` returns the champion version and frozen P1/P2 staffing cutoffs — matching this README because the served artifact and these numbers come from the same promoted `model_meta.json`.

![Agent calls get_model_status: champion version, cutoffs, ranking and calibration](docs/img/01-mcp-model-status.png)

**2 · Score → banded action.** An SP→Bahia order at first scan: blown ship limit, 38% recent seller late rate, 4.25 days left on the promise. The policy answers with band **P1**, a remaining-leg upgrade priced ~$23, and `requires_human_approval: true` — spend above $20 is not autonomous. Note the agent's own read: the policy is a band + eligibility rule, **not** a max-NPV picker — it selected the upgrade even though a cheaper action carried higher expected net value in the same payload.

![Agent calls recommend_policy_action: P1 band, upgrade action, human approval required](docs/img/02-decision-p1-upgrade.png)

**3 · Why this order.** Tree SHAP on the booster (pre-calibration): remaining promise days and handling fraction dominate — clock and distance, not basket size.

![Agent calls explain_promise_miss: top risk drivers](docs/img/03-shap-risk-drivers.png)

**4 · Simulated execution — including when it fails.** This seeded draw's upgrade did **not** prevent the miss: cost $23.29, zero delay-days avoided, net −$23.29. Ex-ante expected value is not the same as an ex-post draw; the simulation reports both honestly rather than always crediting the intervention.

![Simulated execution: intervention failed this draw, net negative, seed recorded](docs/img/04-simulated-execution.png)

**5 · The agent cannot pick a cheaper action.** Executing anything other than the ledgered policy decision is refused by the server — the copy-the-action contract is enforced, not advisory.

![Server refuses AT_RISK_NOTICE: not the frozen policy action for this decision](docs/img/05-policy-refusal.png)

**6 · Lineage.** One append-only chain per order — prediction → decision → action → outcome, linked by ids. The blocked cheaper execute never created an action row.

![Decision ledger lineage for the order](docs/img/06-decision-lineage.png)

**7 · Live traffic on the platform dashboard.** A 2,000-request scored replay through the IAM-gated endpoint: 100% HTTP 200, **p95 162 ms** — under the repo's own 200 ms canary gate. The ~1-minute lines in the latency tile are held-open **agent MCP streaming connections**, not inference latency (Cloud Run can't split the two by label — one service, one auth boundary, one telemetry stream; the in-process `/v1/metrics` counters and the ledger are what separate app from agent traffic). Billable instance time shows scale-to-zero before and after.

![Cloud Monitoring: request plateau, p95 latency, scale-to-zero billable time](docs/img/07-cloud-monitoring.png)

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

Champion **`local-20260819T170145Z`** (calibrated XGBoost, 100 Optuna trials; late rates use observed customer delivery only; validation split in half so calibration/early-stopping and threshold-freezing never share rows). Test **n = 14,471**, promise-miss rate **4.6%**.

Lead with **exception-queue lift** (how much better the work list is than a random draw), then ranking/calibration. Accuracy on a rare miss is the wrong headline.

| Capacity (test) | Precision | Recall | Lift vs 4.6% base |
|---:|---:|---:|---:|
| Top 2.5% (P1-sized queue) | **46.0%** | 24.8% | **10.0×** |
| Top 10% (P2-sized queue) | **22.5%** | 48.7% | **4.9×** |

Among the highest-risk fortieth of later orders, about **2 in 5** actually miss the promise. The top tenth captures about **half** of test misses. That is the capacity story for a NOC: scarce attention, ranked work.

| Ranking / calibration | Test | Bootstrap 95% CI |
|---|---:|---|
| PR-AUC | **0.310** | 0.276 – 0.343 |
| ROC-AUC | **0.827** | 0.807 – 0.844 |
| Brier | 0.037 | 0.034 – 0.040 |
| ECE | 0.004 | — |

The validation window is split in half by time: the earlier half fits early stopping and isotonic calibration; the later half — untouched by any fitting — freezes the policy cutoffs and is what "validation" metrics report (PR-AUC **0.356**, ROC-AUC **0.820**, miss rate 4.8% vs 4.6% on test). Thresholds stay frozen rather than being re-fit on later traffic, so the queue definition does not silently drift with the base rate.

Policy cutoffs from held-out validation scores: **P1 = 0.5000**, **P2 = 0.2471**.

---

## Adopted workflow (policy) and governed agents

The model does not pick the action. A versioned policy (`noc-handoff-policy-v1`) is the contract ops and agents both consume — the analog of a governed metric: humans own the definition, tools query it.

| Band | Rule | Workflow action |
|---|---|---|
| **P0** | Remaining days to promise ≤ 0 | `LATE_NOTICE` (already late; clock rule, not a ranker) |
| **P1** | Score ≥ 0.5000 | `REMAINING_LEG_UPGRADE` if eligible, else `AT_RISK_NOTICE` |
| **P2** | Score ≥ 0.2471 | `AT_RISK_NOTICE` |
| **P3** | Else | `NO_ACTION` |

Upgrade eligibility (demo proxy, not a carrier SKU): P1 **and** `0 < remaining ≤ 7` days **and** (`geo ≥ 100 km` **or** not same state). Intervention cost ≥ **$20** waits for a person — high-stakes model-adjacent spend is not autonomous.

LangGraph **copies** `recommended_action` (it does not re-argmax EV). Documented MCP tools are the skill surface (score, explain, recommend, simulate). `execute_simulated_action` / `POST /v1/action/simulate` take a named action and reject it unless it matches the ledger's frozen policy decision. Human review remains on promote / retrain / spend ≥ $20.

### Unit economics in simulation — not claimed P&L

Versioned placeholders (`econ-sim-v3`) so a stakeholder conversation can happen in **cost per miss / cost per intervention**, not only PR-AUC:

```text
miss_cost     ≈ $10 + 10% of basket          (goodwill + value-at-risk stub)
upgrade_cost  ≈ freight-scaled placeholder   (clip $5–$80; not a carrier tariff)
notices       ≈ $1, 0% OTIF recovery in sim  (customer-impact only; days late unchanged)
upgrade prevent rate ≈ 0.35                  (assumed Bernoulli, not fitted lift)
delay days    ≈ observed (delivery − EDD)+   (0 if upgrade “succeeds”; else unchanged)
                 fallback 6d median on misses when overrun is not passed
```

`allow_causal_roi_claims: false`. Ranking lift above is measured. **Intervention lift is not.** A self-serve experimentation / causal-inference platform is out of scope for this slice and would be the way to replace those assumptions. Real emails, tickets, and carrier APIs stay off (`real_external_execution_enabled: false`). Detail: [`docs/limitations-assumptions-proxies.md`](docs/limitations-assumptions-proxies.md). The rollup that turns those assumptions into “performed X actions, moved Y late deliveries on-time, spent $Z” is `make decision-eval`.

---

## Features (messy ops data, current order excluded)

Grain: one row per `order_id` at first scan. Historical **counts** use prior handoffs with `event_ts < handoff_ts`, current order excluded. `*_late_rate_*` uses only priors whose customer delivery was already observed (`order_delivered_customer_date < current handoff_ts`); the positive class is still `long_delivery` (>14d).

Champion training starts from the pandas builder (`build_feature_table`) and then **consumes the warehouse when it is present** ([`features/historical.py`](src/olist_ml/features/historical.py)): a complete `ml.fct_training_snapshot` export replaces the training table, otherwise a Feast historical retrieval overlays the online seller columns. The overlay joins on `(seller_id, handoff_ts)` — never `seller_id` alone, which would attach a seller's later history to their earlier orders. `snapshot_id` on the model artifact records which path produced it (`pandas_builder`, `feast_historical`, or `dbt_fct_training_snapshot`).

**Request-native (on `/v1/predict`):** basket, freight, item / seller / category counts, payment, customer and seller state, haversine distance, handling days, days remaining to promise, handling as a fraction of horizon, ship-limit miss, purchase clocks.

**Seller / customer / category history:** on the request. `predict_one` hydrates omitted *online seller* fields from Feast when enabled (request values win). Remaining missing history is 0 after that lookup, not instead of it. Replay copies the full history columns into the request.

**Blocked:** reviews; raw carrier or customer delivery timestamps; any window that includes the current order.

Training and serving share column names in [`src/olist_ml/features/contracts.py`](src/olist_ml/features/contracts.py). Feature audit: [`docs/features.md`](docs/features.md).

---

## Serving: REST and MCP

One FastAPI process so REST and MCP cannot diverge on **scoring** (`PredictionService`). Simulate tools take a named action and bind it to the frozen policy row on the ledger. Local: `make serve-local` → `http://127.0.0.1:8080`. Cloud: Cloud Run `olist-ml-api` on GCP (min instances 0, IAM invoker, not `allUsers`). MCP is Streamable HTTP at `POST /mcp` on the **same** URL. When `AUTH_MODE=api_key`, the same header gates REST and `/mcp` (`/health` and `/ready` stay open).

### REST

| Method | Path | Role |
|---|---|---|
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Artifact loaded + `model_version` |
| `GET` | `/v1/model` | Metrics, P1/P2 thresholds |
| `GET` | `/v1/metrics` | In-process counters plus ledger `business_sim` (action mix, late→on-time, spend). Both are per-instance and reset on scale-to-zero — demo telemetry, not durable ops metrics on Cloud Run |
| `POST` | `/v1/predict` | `promise_miss_probability`, `risk_band`, ids |
| `POST` | `/v1/explain` | Tree SHAP on the booster (pre-calibration; displayed `p` is isotonic) |
| `GET` | `/v1/policies/current` | Frozen policy + simulation economics |
| `POST` | `/v1/decision` | Predict → exception policy; optional simulate + ledger |
| `POST` | `/v1/action/simulate` | Frozen policy action; $ sim plus `simulated_delay_days_avoided` |
| `GET` | `/v1/orders/{order_id}/decision` | Prediction / decision / action lineage |
| `GET` | `/v1/actions/{action_id}` | Ledger rows for one action |
| `POST` | `/v1/agent/review` | Copy-the-action LangGraph review (optional human gate); the `agent` extra ships in the serving image, so this runs on Cloud Run |

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
| `execute_simulated_action` | `ActionExecutor` (frozen policy; $ and delay-days sim) |
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

| Concern | Choice | Where it actually runs | Intentionally not |
|---|---|---|---|
| Cloud / warehouse | **GCP, BigQuery, dbt**, Terraform, teardown | Raw CSVs land in the GCS bucket; BigQuery loads **from those objects**; dbt builds the marts | A notebook with a warehouse screenshot |
| Features | **Feast** — offline BigQuery, **SQLite** online | In the Cloud Run request path: the image ships the Feast client + materialized store; lookups fail open | Always-on Redis / Vertex Feature Store (cost) |
| Train / registry | XGBoost + Optuna + isotonic; **MLflow** | Every champion train registers a run and tags `git_sha` / `snapshot_id`; promotion stays a named-human file swap. The *currently published* champion predates this wiring and has no run behind it — see [ARCHITECTURE.md §7](ARCHITECTURE.md) | Notebook cells as the production path; automated promotion |
| Serve | FastAPI + joblib on **Cloud Run** | One `PredictionService` behind REST and MCP | A second inference stack for agents |
| Orchestration | Airflow DAGs as local CLIs (`airflow` extra makes the DAG objects real) | A workstation / local scheduler | Idle Cloud Composer |
| Agents | MCP tools + **LangGraph** copy policy | Both ship in the serving image; the graph copies the frozen action | LLM chooses the exception band |

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
make decision-eval         # action mix / late→on-time / spend (simulated)
make canary-bad            # degraded challenger should fail delayed-label gate

# live GCP (IAM-gated; tear down after the demo)
make gcp-up && make gcp-smoke && make gcp-down
```

Lint: `make lint`. Full local train: `make train-pipeline` — writes a **candidate** under `artifacts/candidates/<version>/`, never the champion path. Serving picks it up only after an explicit, named promote: `make promote-candidate APPROVED_BY=<you>` (H6; appends to `artifacts/promote_record.jsonl`).

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
| `src/olist_ml/outcomes/` | Ledger + simulated impact rollup |
| `src/olist_ml/monitoring/` | Delayed labels, PSI, retrain approval |
| `dbt/` · `feature_repo/` · `pipelines/` · `airflow/dags/` · `terraform/` | Warehouse, features, train graph, jobs, IaC |
| `tests/` · `.github/workflows/` | Unit / API / model tests; CI does not auto-promote |

Interview order: [`ARCHITECTURE.md`](ARCHITECTURE.md) §17. Demo script: [`docs/demo-script.md`](docs/demo-script.md). Runbook: [`RUNBOOK.md`](RUNBOOK.md).

License: MIT. Data: [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) terms.
