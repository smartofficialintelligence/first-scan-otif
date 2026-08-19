# Cost Engineering

Status: locked policy. Update **actuals** after first live demo run.

## Budgets

| Item | Value |
|---|---|
| Hard planning budget | **$75** |
| Target first working MVP demo | **≤ $30** |
| Expected development/demo band | **~$20–$60** |
| Idle target after `demo-down` | **~$0/day** (storage optional cents if data retained) |

## What costs money when left on

| Resource | Idle risk | Off-switch action |
|---|---|---|
| Vertex AI Endpoint | **High** | Undeploy / delete endpoint replicas |
| Memorystore Redis (Feast online) | **High** | Delete instance |
| Cloud Composer (Airflow) | **Very high** | Delete environment or never leave up |
| Cloud Run (min instances > 0) | Medium | Set min=0 or undeploy |
| MLflow Cloud Run | Low–medium | min=0 or undeploy |
| BigQuery storage | Negligible at Olist scale | Optional dataset delete |
| BigQuery queries | Only when jobs run | Stop dbt/pipelines/replays |
| GCS raw/snapshots | Low | Retain as canonical; lifecycle rule optional |
| Artifact Registry images | Low | Retain |

**BigQuery is not the primary cost risk.** Always-on Vertex / Redis / Composer are.

## On / off switches

### `make demo-up` / `demo-down` (local API)

Local uvicorn only. Does not create Cloud Run.

### `make gcp-up` (live serving on)

Intended sequence (no Redis, no Vertex Endpoint, no Composer):

1. Enable Cloud Run / Artifact Registry / Monitoring APIs
2. Apply Artifact Registry (kept across on/off)
3. Build `--target serving` with the champion joblib and push
4. Apply Cloud Run (`min_instance_count = 0`, max 2) + Cloud Monitoring dashboard
5. Wait for `/ready` with an identity token

### `make gcp-down` (live serving off)

1. Terraform apply with `enable_cloud_run=false` and `enable_monitoring=false`
2. Cloud Run service and dashboard are **destroyed**
3. Leave Artifact Registry + GCS + BigQuery + IAM intact for the next `gcp-up`

Idle target after `gcp-down`: **near $0/day** for serving (registry storage is cents).

### `make data-purge` / `make data-restore`

- **purge:** delete BQ datasets + optional ephemeral GCS paths  
- **restore:** reload Olist from canonical GCS → BQ → dbt

## BigQuery cost controls (sufficient; no external-table redesign required)

- Prefer partitioned/clustered marts (`prediction_ts`, `seller_id`)
- Train from immutable snapshots — do not re-scan heavy joins inside Optuna loops
- Cap demo query patterns; avoid `SELECT *` in scripts
- Keep Optuna trials modest (`n_trials` default 25)
- Budget alert on the GCP project

External/BigLake tables over GCS are **optional**, not required for cost at this scale. Canonical GCS + delete-BQ-on-down is enough.

## Development defaults that save money

- CPU-only XGBoost
- Local Airflow / ephemeral runner until Composer demo day
- Feast online store off unless demonstrating online lookup
- Tear down endpoints the same day as the demo
- Separate application deploy from model retrain

## Post-run requirement

After the first complete paid demo, fill in:

- Actual $ by service (Billing export or console)
- What was left on and for how long
- Revised target for next demo

Keep this file honest; do not invent numbers.

## Actuals (first live serving slice, 2026-08-18)

Serving was on for **minutes**, then destroyed. **Do not treat these as a billed invoice** — console $ was not exported. Hours are wall-clock from evidence timestamps.

| Service | Planned estimate | Actual $ | Hours on | Notes |
|---|---|---|---|---|
| BigQuery (query + storage) | TBD | not billed this slice | warehouse already applied | Idle storage only; no dbt/query in this run |
| Vertex AI Endpoint | TBD | **$0** | 0 | Flag stayed off |
| Cloud Run (API) | TBD | not exported | ~0.1 | `olist-ml-api`, min instances 0; created 23:54Z, destroyed 00:01Z |
| Cloud Monitoring dashboard | TBD | not exported | ~0.1 | Destroyed with `gcp-down` |
| Cloud Build (image) | TBD | not exported | job minutes | Nested Docker overlay; image `…/api:20260818T235214Z` |
| Memorystore Redis | TBD | **$0** | 0 | Not created |
| Cloud Composer | TBD | **$0** | 0 | Not created |
| Artifact Registry / GCS | TBD | retain | kept | Registry `olist-ml` left on for the next `gcp-up` |
| **Total** | **≤ $30 target** | **not exported** | | Fill $ from Billing after a paid interview demo |

Idle after `gcp-down`: Cloud Run gone (URI 404). Registry + warehouse remain (cents).

Proof: [docs/evidence/gcp-serving-run.md](docs/evidence/gcp-serving-run.md).
