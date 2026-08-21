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

---

## Run 2 — corrected champion with Feast hydration live (2026-08-21)

Second live run, after the point-in-time fix. What changed versus Run 1: the
serving image now carries the Feast client, the BigQuery-materialized online
store, and the LangGraph extra, and hydration is enabled.

| Item | Value |
|---|---|
| Revision | `olist-ml-api-00006-dzd` |
| Image | `us-central1-docker.pkg.dev/<gcp-project>/olist-ml/api:20260821T213345Z` |
| Image digest | `sha256:8f145c62cee4964fa4f3b1f743f9ff17691244a4f91c83dde568b87e26f7bf9c` |
| Served model | `local-20260821T203846Z` (MLflow run `d1de28a2`, `snapshot_id=feast_historical`) |
| Frozen cutoffs | P1 `0.4895` / P2 `0.2387` |
| Auth | Not public. Identity token as `roles/run.invoker`. App `AUTH_MODE=off` |
| Feast | `FEAST_ONLINE_ENABLED=true`, repo `/app/feature_repo` |

`GET /ready` → `{"ready": true, "model_version": "local-20260821T203846Z", "detail": null}`

Feast startup line from Cloud Run logs, confirming the baked store loaded inside
the container rather than failing open:

```
INFO [olist_ml.features.feast_client] Feast online store ready (repo=/app/feature_repo)
```

`POST /v1/predict` with seller history **omitted**, so the value can only come
from the online store: returned `promise_miss_probability=0.00889`, band `low`,
with a non-zero `feast_lookup_ms` — the lookup ran in the request path.

Online store contents are the BigQuery mart materialized through Feast
(`feast apply` + `materialize`, 3,095 sellers). Offline/online parity passed at
1e-06 for 20 sellers, and the pandas builder now agrees exactly with the
warehouse across all 96,475 rows.

**Freshness caveat, stated plainly.** Olist timestamps end in 2018, so every
online row is far outside the 36h freshness SLA and comes back `stale=True`.
Values are still returned and used, and `stale_feature_rate` is incremented —
the documented degradation path. A live system would materialize continuously;
`make feast-materialize-local --freshen` exists so demos can show the fresh path
without pretending the historical data is current.
