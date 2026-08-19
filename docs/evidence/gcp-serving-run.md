# GCP serving proof

One live Cloud Run + Cloud Monitoring run of the champion promise-miss API.
Turned **on** and exercised. Redis / Vertex Endpoint / Composer were not created.

Captured: `2026-08-19T01:17:59Z` (UTC)

## What was on

| Item | Value |
|---|---|
| Region | `us-central1` |
| Cloud Run service | `olist-ml-api` |
| URI | `https://olist-ml-api-dmkg75dg4a-uc.a.run.app` |
| Image | `us-central1-docker.pkg.dev/<gcp-project>/olist-ml/api:20260819T011400Z` |
| Live revision image | `us-central1-docker.pkg.dev/<gcp-project>/olist-ml/api:20260819T011400Z` |
| Min instances | `0` (Terraform `min_instance_count = 0`) |
| Auth | Not public. Identity token as `roles/run.invoker` (IAM). App `AUTH_MODE=off`. |
| Dashboard | `projects/345139826011/dashboards/c7652114-a27f-4a7b-a414-9839a886a3c0` |
| Dashboard display name | `olist-ml serving and ML` |
| Turned on at | `2026-08-19T01:17:04Z` |

## REST

`GET /health` → `{"status": "ok"}`

`GET /ready` → `{"ready": true, "model_version": "local-20260818T041243Z", "detail": null}`

`GET /v1/model`

- `model_version`: `local-20260818T041243Z`
- `ready`: `True`
- feature count: `40`

Champion artifact baked into the serving image: `artifacts/model.joblib` (`local-20260818T041243Z` when this proof was first recorded).

## MCP

Streamable HTTP on the same Cloud Run service (`POST /mcp`, identity token). Same `PredictionService` as REST.

```
mcp_http model=local-20260818T041243Z p=0.0171 band=low
```

## Holdout replay through Cloud Run

50 chronological holdout events, HTTP `POST /v1/predict`, identity token.

| Metric | Value |
|---|---|
| Rows | 50 |
| HTTP 200 | 50 |
| model_version values | local-20260818T041243Z |
| p95 latency_ms (client) | 81.2 |

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
