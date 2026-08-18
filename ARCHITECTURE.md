# System architecture

Interview reference for this repository. Read this first; the other docs are supporting detail.

This system scores **whether an Olist order will miss its customer-facing delivery promise**, at the moment the parcel first hits the carrier. That score feeds a **fulfillment exception queue** (notice, remaining-leg upgrade proxy, or no action). The same scoring path is used for REST, MCP, training, and replay. Nothing here is a notebook that happens to have an API bolted on.

---

## 1. What this is, and what it is not

**Is:** a production-shaped ML platform slice on GCP (and a fully local path that does not need GCP). It covers features, training, registry, serving, canary, delayed-label quality, drift, human-gated retrain, and a deterministic decision layer with a thin agent that **executes** policy rather than inventing it.

**Is not:**

- A causal ROI study. Simulated dollars are labeled simulation. The config flag `allow_causal_roi_claims` is false.
- A live marketplace. There is no organic production traffic. Canary, drift, and delayed labels are demonstrated by **replaying a chronological holdout of real Olist orders**.
- An LLM operations bot. The LangGraph agent copies the frozen policy action. No model chooses the band.
- An all-Vertex product. Vertex trains and can host the model; features, tracking, and orchestration are separate open tools on purpose.

**Dataset:** public [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Orders, items, payments, customers, sellers, products, geolocation.

**Primary region (when cloud is on):** `us-central1`.

---

## 2. The operational job

Imagine a network operations center for last-mile exceptions.

At **first carrier scan**, the seller’s work is done. The remaining lever is the **rest of the journey** (and customer communication). The model does not “predict late packages in general.” It answers:

> Given what we know at this scan, how likely is this order to arrive **after the date we already promised the customer**?

That is an OTIF / promise-miss question, not a duration question. Duration (“will this take more than 14 days?”) mostly reconstructs the public ETA. Promise-miss asks whether **we will break the promise we already made**.

**Who uses the output**

| Role | What they get |
|---|---|
| Exception queue | Ranked work: already-late notices, a small high-risk upgrade-proxy band, a larger at-risk notice band |
| Serving / platform | `promise_miss_probability`, risk band, `model_version`, timestamps |
| Agents / tools | Same scores via MCP; same policy recommendation; simulated action only |

Capacity is the business story: on the later test window (~4.6% miss rate), the top 2.5% by score is about **9×** a random draw; the top 10% captures about **half** of misses at ~5× enrichment. Ranking metrics (PR-AUC) are appendix. Lead with queue precision and remaining-leg window.

---

## 3. The decision, locked

| Question | Answer |
|---|---|
| Entity | One row per `order_id` |
| When we score | First carrier scan: `handoff_ts = order_delivered_carrier_date` |
| Approval clock | `prediction_ts = order_approved_at` (else purchase time). Used for **handling and horizon**, not for the train/test cut |
| Label | `promise_miss = customer_delivery > order_estimated_delivery_date` |
| Never in X | Raw carrier timestamp, raw customer delivery, reviews, anything after the scan. **Derived clocks** at the scan are allowed |
| History windows | 7 / 30 / 90 day rates, events strictly **before** `handoff_ts` |
| Output | Calibrated `P(promise_miss)` + risk band + persisted policy thresholds |
| Policy | Deterministic bands P0–P3 (`noc-handoff-policy-v1`) |
| Agent | Copies `recommended_action`. Does not re-choose |
| External side effects | Off. Simulated ledger only |

Published local champion `local-20260818T041243Z` (8 Optuna trials, test n=14,471):

| Metric | Test |
|---|---|
| PR-AUC | 0.296 (bootstrap 95% CI ~0.26–0.33) |
| ROC-AUC | 0.816 |
| Miss rate | 4.6% |
| Brier | 0.038 |
| ECE | 0.019 |

Policy cutoffs are **frozen validation score thresholds** (P1 ≈ 0.56, P2 ≈ 0.32), not live percentiles of today’s traffic. The later test book has a lower miss rate than validation (12.3% → 4.6%). That shift is part of the story, not something to hide.

### Why not the earlier targets

| Attempt | What it actually learned | Why it is not the hero |
|---|---|---|
| Promise-miss **at approval** | Weak residual (~0.10–0.22 PR-AUC) | The public ETA already ate geo and horizon |
| Duration > 14 days from approval | Stronger ranker (~0.53 PR-AUC) | Most long orders were **promised** long. Reconstructs ETA, not a broken promise |
| Promise-miss **at first scan** | Usable ranker (~0.30 PR-AUC) on a ~5% later-period event | Clocks that are illegal at approval become legal: handling time, days left on the promise, seller missed ship-limit |

Duration (`long_delivery`) remains a **diagnostic** label and the point-in-time source for columns named `seller_late_rate_*` (Feast contract kept those names). It is not what the API optimizes.

Recorded in [docs/adr/0006-handoff-promise-miss-noc.md](docs/adr/0006-handoff-promise-miss-noc.md).

---

## 4. End-to-end, one picture

```text
Public Olist CSVs
        │
        ▼
  Load (local fixtures, or GCS → BigQuery)
        │
        ▼
  dbt: staging → intermediate → ML marts
  (labels, PIT history, geo, training snapshot)
        │
        ▼
  Feast registry
  ├── offline: training retrieval
  └── online: seller features (Redis when demo-on; SQLite / request fields when off)
        │
        ▼
  Train (local pipeline or Vertex)
  XGBoost + Optuna (PR-AUC) → isotonic calibration on frozen valid
        │
        ▼
  MLflow: REGISTERED_CANDIDATE   ← automation stops here
        │
        │  person reviews offline gates
        ▼
  Serve: PredictionService
  REST (Cloud Run / uvicorn)  and  MCP  share this object
        │
        ├─ request-native features (basket, geo, handoff clocks)
        ├─ optional Feast get(seller_id)
        └─ model artifact or Vertex endpoint
        │
        ▼
  Deterministic policy  →  recommended action
        │
        ▼
  Agent copies that action  →  simulated executor  →  ledger
        │
        ▼
  Operate (no live users):
  replay holdout → hold labels 7 days → release → delayed PR-AUC
                 → feature PSI / high-band mix
                 → person approves retrain → new candidate
                 → person approves promote (never automatic)
```

Two clocks matter and are easy to mix up in an interview:

```text
prediction_ts   approval (or purchase)     handling, horizon, freight known
handoff_ts      first carrier scan         when we score; split key; PIT cutoff
customer_delivery                          LABEL ONLY — never a feature
```

---

## 5. Tech stack and the tradeoffs

Intentionally **not** “everything is Vertex” and **not** Databricks.

| Concern | Choice | Why | Rejected / deferred |
|---|---|---|---|
| Cloud | GCP | Real IAM, Terraform, teardown; transferable platform seams | Databricks Free Edition is cheaper and hides seams; see [docs/adr/0001-gcp-not-databricks.md](docs/adr/0001-gcp-not-databricks.md) |
| Warehouse | BigQuery | Native dbt, cheap at Olist scale | Spark/Databricks lakehouse |
| Transforms | dbt Core | Tested, reviewed SQL; serving must reproduce the same definitions | Train-only pandas feature scripts as source of truth |
| Feature store | Feast (BQ offline, Redis online for demos) | Offline/online contract + freshness; SQLite for demo-off | Vertex Feature Store as the primary store (less portable) |
| Training jobs | Vertex Pipelines **or** `pipelines/local_pipeline.py` | Same step graph: validate → tune → train → calibrate → evaluate → register | Notebook cells as the production path |
| Experiments / registry | MLflow | Version, tags, candidate lifecycle | Vertex Experiments / Model Registry as the system of record |
| Model host | Joblib locally; Vertex Endpoint when cloud serving is on | Managed traffic split when you pay for it | Always-on endpoint |
| App | FastAPI on Cloud Run (min instances 0) | REST + MCP over **one** `PredictionService` | Separate inference stacks per interface |
| Orchestration | Airflow DAGs as **local Python entrypoints**; Composer only for a live demo window | Cross-system jobs (replay, labels, drift, retrain) without a $ idle Composer bill | Always-on Composer |
| IaC | Terraform modules, apply **off** until a person reviews the plan | IAM and public exposure are risk-bearing | CI `terraform apply` |
| CI | GitHub Actions: lint, test, dbt parse, terraform validate, Docker build | App deploy does **not** retrain; train workflow is manual dispatch | Retrain-on-every-PR |

**Why split Feature store / MLflow / Airflow / Vertex instead of one vendor lifecycle:** the interview story is ownership boundaries. dbt defines features. Feast serves them. Vertex runs the heavy train/serve jobs. MLflow is the model truth. Airflow is the calendar and the alarm bus. The cost of that split is more moving parts, paid for with a local-first path and teardown discipline ([docs/adr/0002-feast-mlflow-airflow-vertex.md](docs/adr/0002-feast-mlflow-airflow-vertex.md)).

**Why XGBoost + Optuna + isotonic, not a deep model:** tabular, CPU, calibration-friendly, modest trial budget (25 on full data, fewer on fixtures). No SMOTE on the production path (it fights calibration). Class imbalance uses `scale_pos_weight`.

**Why PR-AUC as the training metric, not accuracy:** positives are rare (about 8% overall, 4.6% on the later test window). Accuracy is a trap. Production *service* metrics are latency, errors, volume, freshness, drift, and **delayed-label** ranking — different from training metrics on purpose.

---

## 6. Data and features

Grain: one ML row per order at first scan.

```text
raw CSVs
  → staging (clean, typed)
  → intermediate (order summary, seller/customer/category history, geo)
  → marts/ml (feature table, labels, training snapshot)
```

**Request-native (known at the scan, sent on `/v1/predict`):** basket, freight, item/seller/category counts, payment, customer/seller state, haversine distance, handling days, days remaining to the promise, handling as a fraction of horizon, ship-limit miss, purchase clocks.

**Historical (point-in-time, current order excluded):** seller order counts and late rates (7/30/90d) — also the **online** Feast subset. Customer and category history exist offline; v1 online lookup is seller-only.

**Blocked:** reviews; raw delivery timestamps; any window that includes the current order or closes on the right.

**Training–serving consistency:** `src/olist_ml/features/contracts.py` is shared. Offline rows come from the dbt snapshot / Feast historical path, not a second feature dialect. A parity test compares offline vs online seller values when Feast is on.

**Stale online features:** seller SLA for demos is 36 hours. If lookup is stale, still predict with fallback priors and increment `stale_feature_rate`. Freshness timestamp and Feast lookup milliseconds are **always keys on the prediction log** (null / 0 when Feast is off).

Feature audit: [docs/features.md](docs/features.md), [docs/h2-feature-audit.md](docs/h2-feature-audit.md).

---

## 7. Training and model lifecycle

```text
TRAINED → EVALUATED → REGISTERED_CANDIDATE
        → (person) APPROVED_FOR_CANARY → CANARY → (person) CHAMPION
                ↘ ROLLED_BACK → SUPERSEDED
```

Automation **does not** set champion. Local: `make train-pipeline` or `make airflow-train-local` (the latter is the unconstrained demo train; it does not check retrain-approval). Production-shaped retrain is a **different** job: it requires an approval file, and if the reason is drift it also requires an active drift alarm.

**Pipeline steps:** validate data contracts → Optuna on train (maximize PR-AUC) → fit → **isotonic calibration on frozen validation** (`CalibratedClassifierCV` + frozen estimator) → evaluate on test → log MLflow → tag `REGISTERED_CANDIDATE`.

**Offline gates before canary (defaults, tunable):** PR-AUC within 0.01 of champion; Brier not worse than champion + 0.02; ECE ceiling; no large-support segment collapse; p95 predict latency smoke. Fail → stay evaluated / rejected. Numbers live in [docs/gate-defaults.md](docs/gate-defaults.md).

**Calibration language for interviews:** Brier is mean squared error on probabilities. ECE is expected calibration error (reliability vs predicted confidence). Both are reported because a useful queue needs ranking **and** probabilities you can threshold.

Artifacts: `artifacts/model.joblib` + `model_meta.json` (gitignored). Meta stores feature names, metrics, git SHA, snapshot id, and the P1/P2 score thresholds.

---

## 8. Serving

One object: `PredictionService` (`src/olist_ml/inference/predictor.py`).

```text
Client
  → FastAPI  (or MCP stdio)
       → auth (API key when AUTH_MODE=api_key; open for local)
       → schema validation (PredictRequest)
       → assemble features (request + optional Feast)
       → predict / explain
       → metrics counters
  → JSON: probability, risk_band, model_version, prediction_id, timestamps
```

**REST (locked surface):** `/health`, `/ready`, `/v1/model`, `/v1/predict`, `/v1/explain`, `/v1/metrics`, plus decision routes (`/v1/decision`, `/v1/action/simulate`, agent review, current policy).

**MCP:** `predict_promise_miss`, `explain_promise_miss`, status/metrics, and decision tools. No second scorer.

**Explain:** SHAP on a sampled/synchronous path with a latency budget. Not on the hot path for every canary event.

**Local:** `make serve-local` (uvicorn :8080). **Cloud:** Cloud Run in front of the same app; optional Vertex Endpoint behind `PredictionService` when serving modules are applied. Terraform serving modules default **off**.

---

## 9. Policy and the agent

Scoring and acting are separate systems. The model does not pick an action.

```text
promise_miss_probability
        │
        ▼
  Band (clock + frozen thresholds)
        P0  remaining ≤ 0              → LATE_NOTICE          (not a ranker)
        P1  score ≥ P1 threshold       → upgrade if eligible, else AT_RISK_NOTICE
        P2  score ≥ P2 threshold       → AT_RISK_NOTICE
        P3  else                       → NO_ACTION
        │
        ▼
  Upgrade eligibility (assumptions, not carrier SKUs):
        P1
        and 0 < remaining_to_promise_days ≤ 7
        and (geo ≥ 100 km or not same state)
        │
        ▼
  recommended_action
        │
        ▼
  LangGraph agent  (no LLM)
        copies recommended_action
        if upgrade_cost ≥ 20 → wait for a person
        else simulated ActionExecutor → JSONL ledger
```

Expected value of actions is computed as an **appendix** for curiosity. The hero path is **not** argmax EV. That was an earlier spec; it was retargeted because a NOC should be explainable: “already late,” “tiny expensive queue,” “notify,” “ignore.”

**Economics are versioned placeholders** (`config/policy_economics.yaml`, `econ-sim-v3`):

- Miss cost ≈ $10 + 10% of basket (goodwill lump, not estimated from Olist).
- Upgrade cost ≈ a lognormal draw around **half of observed freight**, clipped. Freight is **not** an express SKU; it only scales the placeholder.
- Notices: cheap, **zero** OTIF recovery in sim (customer-impact reduction only).
- Prevention rate on an eligible upgrade is an assumed Bernoulli (e.g. 0.35), not a fitted lift.

Do not present simulated net as P&L. Detail: [docs/limitations-assumptions-proxies.md](docs/limitations-assumptions-proxies.md).

---

## 10. Operating the model (the part that is not “train and forget”)

There is no production firehose. Honesty is a **deterministic replay** of a late chronological holdout (~10% of labeled orders) that **never trains**. Same seed + snapshot → same request order. Contract: [docs/simulation.md](docs/simulation.md).

### 10.1 Prediction log

Each replay row includes model version, latency, HTTP status, probability, risk band, traffic bucket (90/10 by hash of `order_id`), snapshot, scenario, seller/geo features used for drift, `feature_freshness_ts`, `feast_lookup_ms`, and delayed-label fields. Completeness vs that minimum list is flagged on the row.

### 10.2 Labels arrive later

Ground truth exists in history, but the demo must show **you do not score quality on day zero**.

```text
label_release_at = prediction_timestamp + 7 days
label_released   = false until a release job
```

Replay may store `label_promise_miss` immediately (historical truth). **Quality jobs ignore it until release.** `scripts/release_labels.py` flips the flag when a virtual “now” passes `label_release_at`. Short demos use a far-future virtual clock.

Delayed eval computes PR-AUC and Brier on **released rows only**. Quality alarm: drop **> 0.03** vs a rolling baseline. Canary ranking gate: delayed PR-AUC **≥ champion − 0.02**.

This is the difference between “we logged the answer we already had” and “we waited, then judged ranking.”

### 10.3 Canary and rollback

```text
champion 100%
  → deploy challenger artifact
  → 90 / 10 by order_id hash (stable; not random per request)
  → replay
  → release labels
  → compare delayed PR-AUC + latency + HTTP
  → recommend ROLLBACK or hold for a person
```

A **bad canary** is an intentionally inverted/degraded copy of the champion (`scripts/create_bad_challenger.py`). `make canary-bad` is supposed to fail the delayed-label gate and recommend 100% champion. Scripts never change traffic themselves.

### 10.4 Drift is not quality

| Signal | What moved | What we do |
|---|---|---|
| Feature PSI > 0.2 on seller late rates, seller counts, or geo | Input population | Alarm. Investigate. Maybe retrain **after a person approves**. Not rollback. |
| High-risk band mix shifts > 20% relative | Score mix | Same: alarm only |
| Delayed PR-AUC drop > 0.03 | Outcomes, once labels exist | Quality alarm; canary / promote decision |

Named scenarios **mutate features** before scoring:

- `drift_seller_late` — ×1.5 on seller late-rate columns (cap 1.0) for 30% of rows
- `drift_geo` — +50% `geo_distance_km` on 30% of rows
- `baseline` / `bad_canary` — no feature shift

`make drift-geo` writes a baseline log, a drifted log, then PSI. Unit tests assert those scenarios can push PSI through 0.2.

### 10.5 Retrain

```text
drift alarm file          ≠  start training
monthly calendar          ≠  start training without a person
approve-retrain file      +  (alarm if reason is drift)  →  training pipeline
output                    =  REGISTERED_CANDIDATE
promote to champion       =  a later, separate person decision
```

`make airflow-train-local` is the **demo** train (M4-style, no approval check). `make retrain-trigger` is the **contract** path. Do not confuse them in an interview.

App deploy CI does not train. Train CI (`train-model.yml`) is manual dispatch and does not deploy.

### 10.6 Dashboards

Local: `make export-monitoring` → `artifacts/monitoring_dashboard.json` (volume, errors, latency, mix, stale features, last drift and delayed-eval snapshots).

GCP: Terraform module under `terraform/modules/monitoring` (Cloud Run request count / p95 / instance time, plus a text panel for the ML signals). Flag `enable_monitoring` defaults **false**, same as serving. Applying it is a real infra change.

---

## 11. Orchestration surface

Airflow is the **job names and the local CLIs**, not a billable Composer cluster left on overnight.

| Job | Does |
|---|---|
| Replay holdout | Score traffic → prediction log |
| Release labels | Flip `label_released` by virtual now |
| Delayed eval | PR-AUC / Brier on released rows |
| Drift check | Feature PSI + high-band mix → alarm JSON |
| Retrain trigger | Approval (+ alarm if drift) → candidate |
| Train (demo) | Unconstrained local pipeline |
| Decision eval | Ledger summary; not model quality |

Composer, if used at all, is created for the demo window and deleted in teardown.

---

## 12. Approvals people still make

Automation stops at risk-bearing steps. Other files in this repo number them; **use the English names in conversation.**

| Decision | Why a person |
|---|---|
| Problem, clocks, metrics | Changing the label or prediction time is a product change |
| Feature / leakage audit | Done for v1; new columns need the same bar |
| Offline candidate is good enough for canary | Metrics lie; segments lie; you look |
| Canary → 100% traffic | Delayed labels + latency; still a traffic change |
| Alarm → actually retrain | Drift ≠ broken model |
| Candidate → champion | Retrain is not promote |
| `terraform apply` / IAM / public exposure | Money and security |
| Rollback | Logged, even if the same operator |
| Economics numbers | Approved as **simulation defaults**, not measured lift |
| Agent may spend on an upgrade | Spend threshold (placeholder $20) |
| Real emails, tickets, carrier APIs | **Forbidden** (`real_external_execution_enabled: false`) |

---

## 13. Cost and demo switches

Planning budget ~$75; first working cloud demo aimed ≤ $30; idle after teardown **near $0/day**.

**What actually burns money if left on:** Vertex Endpoint, Memorystore Redis, Cloud Composer. BigQuery storage at Olist scale is noise. Queries cost only when jobs run.

```text
make demo-up      local API today; GCP pieces gated on apply
make demo-down    stop local API; remind to undeploy endpoint / Redis / Composer
```

Canonical data at rest when cloud is off: GCS (and/or gitignored `data/raw`). Prefer deleting demo BigQuery datasets on the way down; restore is load + dbt.

[COST.md](COST.md) still has **placeholder actuals** until a paid demo is billed. Do not invent numbers.

---

## 14. What runs fully local vs what needs a person + GCP

**Local (default interview path):** fixtures → tests → train → uvicorn → MCP → decision/agent harness → replay → release labels → delayed-label canary → drift scenario → approve retrain → new candidate. No bill.

**Needs credentials + an apply someone reviewed:** live BigQuery/dbt, Feast Redis, Vertex endpoint, Composer, Cloud Monitoring dashboard, Cloud Run in the project.

Terraform **validate** runs in CI. Terraform **apply** does not.

---

## 15. Explicit non-claims (say these out loud)

- Simulated net value is not causal ROI and not observed P&L.
- `freight_value` is not a paid remaining-leg product.
- Upgrade cost and prevention rate were not fit on Olist.
- Feast freshness is logged even when Feast is off (empty timestamp, 0 ms).
- Holdout replay is a substitute for production traffic, not production traffic.
- A green unit test that PSI can alarm is not “we detected drift in Brazil last Tuesday.”

---

## 16. Code map

| Path | Role |
|---|---|
| `src/olist_ml/data/` | Load, labels, temporal splits |
| `src/olist_ml/features/` | Contracts, assembler, Feast client, handoff clocks |
| `src/olist_ml/training/` | Tune, train, calibrate, evaluate, package, offline gates |
| `src/olist_ml/inference/` | `PredictionService` |
| `src/olist_ml/api/` | FastAPI + MCP |
| `src/olist_ml/decisions/` | NOC policy, economics, routing |
| `src/olist_ml/agents/` | LangGraph copy-the-action graph |
| `src/olist_ml/actions/` | Simulated executor |
| `src/olist_ml/monitoring/` | Metrics, PSI, drift, delayed labels, retrain approval, export |
| `src/olist_ml/canary/` | 90/10 split, degraded challenger |
| `dbt/` | Warehouse transforms and tests |
| `feature_repo/` | Feast definitions |
| `pipelines/` | Local + Vertex train graph |
| `airflow/dags/` | Job entrypoints (work without Composer) |
| `terraform/` | GCS, BigQuery, IAM, optional Cloud Run / Vertex / monitoring |
| `scripts/` | Replay, labels, canary, drift scenarios, demos |
| `tests/` | Unit, model, API |
| `.github/workflows/` | `ci.yml` (every PR); `train-model.yml` (manual, no deploy); `deploy-api.yml` (stub, no train); `infra.yml` (validate, no apply) |

---

## 17. How to walk this in an interview (suggested order)

1. **Job:** exception queue at first scan, not “accuracy on late packages.”
2. **Clocks:** split and PIT on handoff; customer delivery is the label; derived handling/remaining clocks are legal only at the scan.
3. **Why this label:** duration reconstructed ETA; approval-time miss was too weak; scan-time miss is the OTIF question.
4. **Seams:** dbt / Feast / MLflow / Airflow / Vertex / Cloud Run — and why they are not one product.
5. **One scorer:** REST and MCP share `PredictionService`.
6. **Policy vs agent:** bands are deterministic; agent copies; EV is appendix; no causal $ claims.
7. **Operate:** holdout replay, labels seven days later, PSI ≠ PR-AUC, alarm ≠ retrain, retrain ≠ champion, deploy ≠ train.
8. **Cost:** endpoints and Composer kill budgets; teardown is part of the design.

Demo script: [docs/demo-script.md](docs/demo-script.md). Runbook: [RUNBOOK.md](RUNBOOK.md). Binding table form of the same decisions: [docs/LOCKED_DECISIONS.md](docs/LOCKED_DECISIONS.md).

---

## 18. Abbreviations you may see in other files

This architecture narrative does not depend on them. Older notes number human approvals and build slices. If you open those files:

| You might see | Means |
|---|---|
| Problem / feature / economics “gates” numbered in locked-decisions | The person-approvals table in §12 |
| Build slices numbered in milestones.md | Local model → BQ/dbt → Feast → train/registry → serve → MCP → CI → monitoring → canary → Airflow jobs → polish |
| Retrain-approval file / “approve-h5” Make target | Person must approve retrain (§10.5) |
| Promote-after-retrain | Person must promote a candidate to champion — not the train job |
| Monitoring slice | Exported metrics + optional Cloud Monitoring module (§10.6) |
