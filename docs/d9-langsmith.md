# D9 — LangSmith tracing (optional)

Local agent evals do **not** require LangSmith. Cloud tracing is opt-in.

## Enable

```bash
uv sync --extra agent
export LANGSMITH_API_KEY=...          # or LANGCHAIN_API_KEY
export LANGCHAIN_PROJECT=olist-ml-agent   # optional
# unset or set LANGCHAIN_TRACING_V2=false to disable
```

### Cloud Run (Terraform — no manual gcloud)

When `enable_serving=true`, Terraform:

1. Creates runtime SA `${name_prefix}-api`
2. Grants `roles/secretmanager.secretAccessor` on secret `langsmith_secret_id` (default: `langsmith-api-key`)
3. Mounts secret → env `LANGSMITH_API_KEY` on Cloud Run
4. Sets `LANGCHAIN_PROJECT` and `LANGCHAIN_TRACING_V2=true`

Store the key in Secret Manager as a **raw string** (not JSON). Override names in `terraform.tfvars` if needed:

```hcl
langsmith_secret_id = "langsmith-api-key"
langsmith_project   = "olist-ml-agent"
```

Then `terraform apply` after H7 review.

Agent review (`run_agent_review` / `POST /v1/agent/review`) configures tracing when a key is present and returns a `langsmith` status block:

```json
{"enabled": true, "project": "olist-ml-agent", "reason": "configured"}
```

Without a key:

```json
{"enabled": false, "project": "olist-ml-agent", "reason": "no_api_key_or_explicitly_disabled"}
```

## Local evals (always)

```bash
make agent-evals
# → artifacts/agent_eval_report.json
```

Deterministic policy-compliance checks live under `evals/` and are the deployment gate for invalid actions (must be 0 failures).
