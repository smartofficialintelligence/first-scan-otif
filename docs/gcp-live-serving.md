# Live GCP serving (turn-key)

Cloud Run + Artifact Registry + Cloud Monitoring, with an explicit on/off.

This is the **live serving proof** path. It is not Redis, not a Vertex Endpoint, not Composer, and not a public URL.

## On / off

```text
make gcp-up        # enable APIs, keep/create Artifact Registry, build+push champion image, apply Cloud Run + dashboard
make gcp-smoke     # REST health/ready/model/predict, MCP on the same artifact, 50-event HTTP holdout replay
make gcp-evidence  # write docs/evidence/gcp-serving-run.md (no secrets)
make gcp-down      # destroy Cloud Run + dashboard; keep Artifact Registry + BQ + GCS + IAM
```

`gcp-down` is what you run when the proof (or interview) is over. Idle serving cost after that is **near zero**. The next `gcp-up` rebuilds and reapplies.

## What turns on

| Resource | Idle behavior |
|---|---|
| Artifact Registry (`olist-ml`) | Kept across on/off (cents; images stay so restore is a push+apply) |
| Cloud Run `olist-ml-api` | **min instances 0**, max 2, 1 vCPU / 1Gi. Destroyed on `gcp-down` |
| Cloud Monitoring dashboard | Destroyed on `gcp-down` |

The serving image is a multi-stage Docker build (`Dockerfile` target `serving`) with `artifacts/model.joblib` + `model_meta.json` baked in. The API scores that joblib in-process. Platform auth is Cloud Run IAM (`roles/run.invoker` for the operator SA). The app itself uses `AUTH_MODE=off`.

Local Docker is used when it works. If overlay/BuildKit fails (nested VMs), `gcp-up` falls back to **Cloud Build** so the same command still produces an Artifact Registry image.

## What stays off

- Redis / Memorystore (Feast online remains SQLite for this demo)
- Vertex AI Endpoint (`enable_vertex_endpoint=false`)
- Cloud Composer / hosted MLflow
- Cloud Run min instances > 0
- `allUsers` invoker (the URI is not a public API)

## Terraform flags

Defaults in `terraform/environments/dev` are **off**:

- `enable_cloud_run` (alias: deprecated `enable_serving`, Cloud Run only — does **not** create Vertex)
- `enable_monitoring`
- `enable_vertex_endpoint`

`make gcp-up` / `gcp-down` pass these flags. Do not apply Vertex or Redis from this path.

## Proof

After a live run, [docs/evidence/gcp-serving-run.md](evidence/gcp-serving-run.md) holds URI, image digest/tag, model version, REST/MCP/replay counts, dashboard id, and the off confirmation. No service-account keys.

## Local vs live

| Command | What it does |
|---|---|
| `make demo-up` / `demo-down` | Local uvicorn only |
| `make gcp-up` / `gcp-down` | Real Cloud Run in the demo GCP project (`GCP_PROJECT_ID`) |

Warehouse (BigQuery / GCS / IAM) is independent: already applied, not destroyed by `gcp-down`.
