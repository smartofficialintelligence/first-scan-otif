# Promise-miss at first carrier scan

Public portfolio artifact on the [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) dataset, on **GCP**.

This is not a notebook with an API bolted on. It is a production-shaped slice: features, training, registry, serving, canary, monitoring, cost-controlled teardown, and a **deterministic exception queue**. At **first carrier scan**, score whether the order will arrive **after the ETA already promised the customer** (OTIF / promise-miss). Policy maps that score plus remaining days into notice, a remaining-leg upgrade proxy, or no action. The agent **copies** that action. It does not choose policy.

Simulated intervention dollars are labeled simulation. They are **not** causal ROI.

## The job

Seller work is done at the first scan. The remaining lever is the rest of the journey (and what you tell the customer). Duration models mostly reconstruct the public ETA. This one asks whether **we will break the promise we already made**.

| Who | What they get |
|---|---|
| Exception queue | Ranked work: already-late notices, a small high-risk upgrade-proxy band, a larger at-risk notice band |
| Serving | `promise_miss_probability`, risk band, `model_version` — same object on REST, MCP, training, and replay |
| Cost / ops | Cloud Run that turns **all the way off** |

Champion `local-20260818T041243Z` (test n=14,471, later-period miss rate **4.6%**):

| Queue (test) | Precision | Lift vs 4.6% |
|---|---:|---:|
| Top 2.5% by score | **41.6%** | **9.0×** |
| Top 10% by score | **22.2%** | **4.8×** |

PR-AUC 0.296 / ROC-AUC 0.816 are appendix. Lead with queue precision and the remaining-leg window. Thresholds are **frozen validation scores** (P1 ≈ 0.56, P2 ≈ 0.32), not live percentiles. Valid miss rate was 12.3%; test is 4.6% — that shift is part of the story.

Business tables: [docs/business_assessment.md](docs/business_assessment.md) · Problem write-up: [docs/ml-problem.md](docs/ml-problem.md) · Assumptions: [docs/limitations-assumptions-proxies.md](docs/limitations-assumptions-proxies.md)

## Policy (locked)

Deterministic bands. Clock rule first, then score.

| Band | When | Action |
|---|---|---|
| P0 | Remaining promise days ≤ 0 | Already-late notice |
| P1 | Score ≥ P1 threshold | Remaining-leg upgrade **proxy** if the window and geography allow it; otherwise at-risk notice |
| P2 | Score ≥ P2 threshold | At-risk notice |
| P3 | Else | No action |

Upgrade is a freight-scaled demo proxy, not a carrier SKU. External side effects are off (simulated ledger only).

## Stack

Interview walkthrough: [ARCHITECTURE.md](ARCHITECTURE.md). Binding tables: [docs/LOCKED_DECISIONS.md](docs/LOCKED_DECISIONS.md).

| Layer | This demo |
|---|---|
| Warehouse / transforms | BigQuery + dbt |
| Feature store | Feast (BigQuery offline; **SQLite** online — Redis would be the shared prod store) |
| Orchestration | Airflow (local DAGs; no Composer required) |
| Training / registry | XGBoost + Optuna, MLflow candidate registry (Vertex train optional) |
| Serving | FastAPI on **Cloud Run** — REST + Streamable HTTP MCP, champion joblib in the image |
| Explain | Tree SHAP on the XGBoost booster; API `p` stays the **calibrated** probability |
| Canary | Chronological holdout replay + delayed labels — not organic traffic |
| Vertex Endpoint / Redis / Composer | **Off** (always-on cost) |

GCP rather than a single lakehouse vendor so the seams (IAM, Terraform, tear-down) are visible: [docs/adr/0001-gcp-not-databricks.md](docs/adr/0001-gcp-not-databricks.md).

## Run it

Local (no GCP bill):

```bash
make sync
make fixtures
make test
make train-local    # or use the published champion in artifacts/ if you have it
make serve-local
# other terminal:
curl -s localhost:8080/health
curl -s localhost:8080/ready
curl -s localhost:8080/v1/model
```

MCP is `POST /mcp` on that same process (Cursor: URL `http://127.0.0.1:8080/mcp`). stdio remains `make mcp-serve`.

Live Cloud Run (no Redis, no Vertex Endpoint). Tear it down the same day:

```bash
make gcp-up && make gcp-smoke && make gcp-evidence && make gcp-down
```

IAM-gated URL, min instances 0. Proof of a live run: [docs/evidence/gcp-serving-run.md](docs/evidence/gcp-serving-run.md). How to hit it from a laptop: [docs/gcp-live-serving.md](docs/gcp-live-serving.md).

Operate-the-model (still local):

```bash
make train-pipeline
make canary-bad          # delayed-label gates → ROLLBACK; never auto-promote
make demo-decision       # predict → frozen policy → agent copies the action → simulated ledger
```

Full public Olist CSVs, when you have them in `data/raw`:

```bash
make download-olist
make train-olist
```

Day-of interviewer sequence: [docs/demo-script.md](docs/demo-script.md) · Commands: [RUNBOOK.md](RUNBOOK.md)

## Cost

`make demo-up` / `demo-down` is local uvicorn only. `make gcp-up` / `gcp-down` is real Cloud Run + a dashboard; Artifact Registry stays so the next up is a rebuild, not a blank project. After `gcp-down`, serving idle is near zero.

Policy: [COST.md](COST.md)

## What this is not

- A live marketplace or organic traffic. Canary, drift, and delayed labels **replay** a chronological holdout of real Olist orders.
- An LLM ops bot. LangGraph executes the **frozen** policy action.
- A causal lift study. `allow_causal_roi_claims` is false.

Automation stops at risk-bearing steps (promote, Terraform apply, retrain approval). See [docs/LOCKED_DECISIONS.md](docs/LOCKED_DECISIONS.md).
