# Milestone 5 — Managed inference

Local + Cloud Run FastAPI share `PredictionService`. Vertex Endpoint is optional behind Terraform `enable_serving`.

## Local demo

```bash
make demo-up          # sync, train if needed, start uvicorn (pid in artifacts/api.pid)
make smoke-local
curl -s http://127.0.0.1:8080/v1/model
# POST /v1/predict and /v1/explain with a PredictRequest body
make demo-down        # kill local API; prints GCP teardown reminders (no deletes)
```

## REST

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | liveness |
| GET | `/ready` | model loaded |
| GET | `/v1/model` | version + feature names + metrics |
| POST | `/v1/predict` | returns `model_version` |
| POST | `/v1/explain` | deterministic stub `top_features` (zeros); SHAP skipped by default |

## Terraform (scaffold only)

- `terraform/modules/cloud_run` — `google_cloud_run_v2_service` + Secret Manager → `LANGSMITH_API_KEY` (see [d9-langsmith.md](d9-langsmith.md))
- `terraform/modules/vertex_endpoint` — `google_vertex_ai_endpoint`
- Wired in `terraform/environments/dev` behind `enable_serving = false` (default)

```bash
make tf-validate   # works with enable_serving=false
```

## Vertex teardown

```bash
uv run python scripts/teardown_endpoint.py          # dry-run (default)
uv run python scripts/teardown_endpoint.py --apply  # needs GCP creds + aiplatform
```

Do not hardcode project secrets; use env / `scripts/materialize_gcp_creds.sh`.
