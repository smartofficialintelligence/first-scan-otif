# GCP serving proof

One live Cloud Run + Cloud Monitoring run of the champion promise-miss API.
Turned **on**, exercised, recorded here, then turned **off**. Redis / Vertex Endpoint / Composer were not created.

Captured: `2026-08-18T23:56:30Z` (UTC)

## What was on

| Item | Value |
|---|---|
| Region | `us-central1` |
| Cloud Run service | `olist-ml-api` |
| URI | `https://olist-ml-api-dmkg75dg4a-uc.a.run.app` |
| Image | `us-central1-docker.pkg.dev/<gcp-project>/olist-ml/api:20260818T235214Z` |
| Live revision image | `us-central1-docker.pkg.dev/<gcp-project>/olist-ml/api:20260818T235214Z` |
| Min instances | `0` (Terraform `min_instance_count = 0`) |
| Auth | Not public. Identity token as `roles/run.invoker` (IAM). App `AUTH_MODE=off`. |
| Dashboard | `projects/345139826011/dashboards/9472f8c6-59c5-4bdd-aa9c-2c64256eb106` |
| Dashboard display name | `olist-ml serving and ML` |
| Turned on at | `2026-08-18T23:55:38Z` |

## REST

`GET /health` → `{"status": "ok"}`

`GET /ready` → `{"ready": true, "model_version": "local-20260818T041243Z", "detail": null}`

`GET /v1/model`

- `model_version`: `local-20260818T041243Z`
- `ready`: `True`
- feature count: `40`

Champion artifact baked into the serving image: `artifacts/model.joblib` (`local-20260818T041243Z` when this proof was first recorded).

## MCP

MCP is stdio (not an HTTP listener on Cloud Run). Smoke used the same local champion artifact the image was built from.

```
mcp_ready model=local-20260818T041243Z p=0.0171 band=low
```

## Holdout replay through Cloud Run

50 chronological holdout events, HTTP `POST /v1/predict`, identity token.

| Metric | Value |
|---|---|
| Rows | 50 |
| HTTP 200 | 50 |
| model_version values | local-20260818T041243Z |
| p95 latency_ms (client) | 78.8 |

Log path (gitignored): `artifacts/prediction_logs_gcp.jsonl`

## Left off on purpose

- Redis / Memorystore (Feast online stays SQLite)
- Vertex AI Endpoint (API scores the joblib in the container)
- Cloud Composer
- Hosted MLflow
- Cloud Run min instances > 0
- Public `allUsers` invoker

## Turn back on later

```text
make gcp-up      # Artifact Registry (kept) + build/push + Cloud Run + dashboard
make gcp-smoke   # REST + MCP + 50-event HTTP replay
make gcp-evidence
make gcp-down    # destroy Cloud Run + dashboard; keep registry + warehouse
```

Warehouse (BigQuery / GCS / IAM) is independent and already applied.


## Turned off

- Timestamp (UTC): 2026-08-19T00:01:34Z
- gcloud run services list names: (none)
- Terraform cloud_run_uri: `null`
- Terraform monitoring_dashboard_id: `null`
- Artifact Registry and warehouse (BQ / GCS / IAM) were left in place so make gcp-up can turn serving back on.

