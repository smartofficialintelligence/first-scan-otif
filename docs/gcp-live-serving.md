# Live GCP serving (turn-key)

Cloud Run + Artifact Registry + Cloud Monitoring, with an explicit on/off.

This is the **live serving proof** path. It is not Redis, not a Vertex Endpoint, not Composer, and not a public URL.

## On / off

```text
make gcp-up        # enable APIs, keep/create Artifact Registry, build+push champion image, apply Cloud Run + dashboard
make gcp-smoke     # REST health/ready/model/predict, Streamable HTTP MCP on /mcp, 50-event HTTP holdout replay
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

Image builds go through **Cloud Build** when local Docker cannot mount overlay (typical in this Cloud Agent: Docker-in-Docker, overlay-on-overlay, `EINVAL` — not a full disk). Do **not** `docker system prune` / delete `/var/lib/docker/overlay2` to “fix” that; the root filesystem is already overlay, so nested overlay mounts will keep failing and a storage reset can take the daemon down. On a laptop with a real ext4/xfs data root, `gcp-up` still tries a local `docker build` first.

## MCP on the same URL

Cloud Run serves **REST and MCP**. `POST /mcp` is Streamable HTTP (JSON). stdio `make mcp-serve` is only for local agent processes.

From the laptop (same identity token as REST, **no** `--audiences` for a user login):

```bash
URI=https://olist-ml-api-dmkg75dg4a-uc.a.run.app
TOKEN=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' \
  "$URI/mcp"
```

Cursor remote MCP config: `"url": "$URI/mcp"` plus `Authorization: Bearer <token>`. Details: [m6-mcp.md](m6-mcp.md).

## Hit the API from a laptop

The URL is on the public internet. IAM is still required (not `allUsers`).

`gcloud auth print-identity-token --audiences=...` **only works for service accounts**. From a user login (`gcloud auth login`), use one of:

```bash
gcloud config set project "$GCP_PROJECT_ID"   # or the demo project id
gcloud run services proxy olist-ml-api --region=us-central1
# other terminal:
curl -s http://127.0.0.1:8080/ready
curl -s http://127.0.0.1:8080/v1/model
```

Or, without `--audiences`:

```bash
URI=https://olist-ml-api-dmkg75dg4a-uc.a.run.app
TOKEN=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOKEN" "$URI/ready"
```

Your Google user must have `roles/run.invoker` on the service (`extra_invoker_members` in Terraform, default includes the operator laptop account).

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
