# First-scan OTIF scoring

At the first carrier scan, is this order likely to miss the promise date? If so, which
operating band should it enter?

That is the whole product. A binary scorer ranks orders at
`handoff_ts = order_delivered_carrier_date`. The label is
`promise_miss`: the customer received the package after the promised ETA.
A frozen policy maps score to P0–P3. An optional agent **copies** that
action; it does not invent a cheaper one. Simulated dollars are a
sensitivity check, not causal ROI.

Olist Brazilian e-commerce data. Decision-science portfolio, not a
carrier production system.

## What it does

1. **Score at first scan.** Champion `local-20260818T041243Z`: test
   PR-AUC **0.296**, ROC-AUC **0.816**, miss rate **4.6%**, Brier
   **0.038**, ECE **0.019**. P1 / P2 cutoffs **0.5625 / 0.3155**.
2. **Put the order in a band.** P0 hold, P1 exception queue, P2 watch,
   P3 no action — deterministic rules (`docs/handoff-policy.md`).
3. **Serve the same scorer.** FastAPI on Cloud Run: `/ready`,
   `/v1/predict`, `/v1/explain` (Tree SHAP), `/mcp` for Cursor.
4. **Operate it.** Replay a bad canary, watch `/ready` fail, promote
   the last good artifact. Tear the stack down when you are done
   (`make gcp-down`).
5. **Do not claim ROI.** `allow_causal_roi_claims: false`. The queue
   table below is ranking quality, not dollars saved.

| Slice (test) | Precision | Lift vs 4.6% base |
| --- | ---: | ---: |
| Top 2.5% | 41.6% | 9.0× |
| Top 10% | 22.2% | 4.8× |

Walkthrough: [`ARCHITECTURE.md`](ARCHITECTURE.md). Business write-up:
[`docs/business_assessment.md`](docs/business_assessment.md). Policy:
[`docs/handoff-policy.md`](docs/handoff-policy.md).

## Run it

```bash
make setup && make data
make serve-local          # FastAPI + /mcp on :8000
# optional live GCP (IAM-gated; tear down after)
make gcp-up && make gcp-smoke && make gcp-down
make canary-bad           # local rollback demo
make demo-decision        # P0 vs P3 + ledger, no LLM
```

Python **3.11+**. `uv` recommended. Tests: `make test`. Lint: `make lint`.

## What is in the repo

| Piece | Role |
| --- | --- |
| BigQuery + dbt | Warehouse + `ml_*` views |
| Feast | Offline Parquet; **SQLite** online (Redis skipped for cost) |
| Champion joblib | Calibrated XGBoost, SHA-pinned |
| FastAPI / Cloud Run | Predict, explain, MCP |
| Terraform | Artifact Registry, Cloud Run, IAM. Vertex, Composer, Redis **off** |
| Decision graph | Copies frozen P0–P3; LangSmith when a tracing key is set |

Live URI is not committed. After `gcp-up`, `gcloud run services describe olist-ml-api --region=us-central1 --format='value(status.url)'`.

Cursor → Cloud Run MCP: IAM invoker + `gcloud auth print-identity-token` as
`Authorization: Bearer …` on `https://<service>/mcp`. Token lasts ~1h.
Do not commit it.

## Limits

- Olist public data, not live carrier events.
- Feast online is SQLite in this demo.
- SHAP is tree-level (pre-calibration); displayed `p` is isotonic.
- No production SLO, no real-money loop.

License: MIT. Data: [Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) terms.
