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

## Actuals placeholder (fill after live demo)

| Service | Planned estimate | Actual $ | Hours on | Notes |
|---|---|---|---|---|
| BigQuery (query + storage) | TBD | TBD | TBD | |
| Vertex AI Endpoint | TBD | TBD | TBD | Tear down same day |
| Cloud Run (API / MLflow) | TBD | TBD | TBD | `min_instances=0` |
| Memorystore Redis | TBD | TBD | TBD | Demo-on only |
| Cloud Composer | TBD | TBD | TBD | Prefer local Airflow; delete if created |
| Artifact Registry / GCS | TBD | TBD | TBD | Retain OK |
| **Total** | **≤ $30 target** | **TBD** | | Update after first paid demo |

Idle after `demo-down`: target **~$0/day** (optional storage cents if data retained).
