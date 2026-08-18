# Milestone 5 — Managed inference

Local uvicorn and Cloud Run FastAPI share `PredictionService`. Vertex Endpoint is optional and **off** by default (`enable_vertex_endpoint`). The turn-key live path is Cloud Run with the champion joblib in the image.

## Local demo

```bash
make demo-up          # sync, train if needed, start uvicorn (pid in artifacts/api.pid)
make smoke-local
curl -s http://127.0.0.1:8080/v1/model
# POST /v1/predict and /v1/explain with a PredictRequest body
make demo-down        # kill local API; prints GCP teardown reminders (no deletes)
```

## Live Cloud Run

```bash
make gcp-up           # Artifact Registry + image + Cloud Run + dashboard
make gcp-smoke        # REST + MCP + HTTP holdout replay
make gcp-evidence     # docs/evidence/gcp-serving-run.md
make gcp-down         # Cloud Run + dashboard off; registry kept
```

See [gcp-live-serving.md](gcp-live-serving.md). Redis is not part of this path.

## REST

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | liveness |
| GET | `/ready` | model loaded |
| GET | `/v1/model` | version + feature names + metrics |
| POST | `/v1/predict` | returns `model_version` |
| POST | `/v1/explain` | deterministic stub `top_features` (zeros); SHAP skipped by default |

## Terraform

- `terraform/modules/artifact_registry` — always applied (cheap idle)
- `terraform/modules/cloud_run` — `google_cloud_run_v2_service`, gated by `enable_cloud_run`
- `terraform/modules/vertex_endpoint` — gated by `enable_vertex_endpoint` (leave false)
- `terraform/modules/monitoring` — gated by `enable_monitoring`

`enable_serving` is a **deprecated alias for Cloud Run only**; it does not create Vertex.

```bash
make tf-validate
make gcp-up / gcp-down   # live on/off
```

## Vertex teardown

```bash
uv run python scripts/teardown_endpoint.py          # dry-run (default)
uv run python scripts/teardown_endpoint.py --apply  # needs GCP creds + aiplatform
```

Do not hardcode project secrets; use env / `scripts/materialize_gcp_creds.sh`.
