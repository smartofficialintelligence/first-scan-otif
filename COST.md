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

### `make demo-up` (on)

Intended sequence:

1. Ensure GCS canonical raw (upload if missing)
2. Create BQ datasets; load raw; `dbt build`
3. Feast apply + offline materialize; start Memorystore; online materialize
4. Ensure MLflow tracking reachable
5. Deploy champion (and optional challenger) to Vertex Endpoint
6. Deploy FastAPI Cloud Run (`min_instances=0` unless demo needs warm start)
7. Optionally start Composer **only if** orchestration demo is in scope
8. Smoke: `/health`, one `/v1/predict`

### `make demo-down` (off)

1. Undeploy Vertex Endpoint (or scale to zero / delete)
2. Delete Memorystore Redis
3. Delete or stop Composer environment if created
4. Undeploy Cloud Run services **or** force `min_instances=0` and confirm no traffic
5. Delete BQ datasets used for demo (optional but preferred for ~$0)
6. Leave GCS + Artifact Registry + Terraform state intact for fast restore

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
