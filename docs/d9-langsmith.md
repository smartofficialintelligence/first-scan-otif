# D9 — LangSmith tracing (optional)

Local agent evals do **not** require LangSmith. Cloud tracing is opt-in on Cloud Run.

## Cloud Run (Terraform — no manual gcloud)

When `enable_serving=true`, `terraform apply` (after H7):

1. Resolves Secret Manager secret `langsmith_secret_id` (default: `langsmith-api-key`)
   - **Existing secret** (your case): leave `langsmith_api_key` unset in `terraform.tfvars`
   - **Terraform-managed value**: set `langsmith_api_key` in gitignored `terraform.tfvars`
2. Creates `${name_prefix}-api` runtime service account
3. Grants `roles/secretmanager.secretAccessor`
4. Mounts secret → `LANGSMITH_API_KEY` on Cloud Run
5. Sets `LANGCHAIN_PROJECT` and `LANGCHAIN_TRACING_V2=true`

```hcl
# terraform/environments/dev/terraform.tfvars (gitignored)
enable_serving = true
# langsmith_api_key = "..."  # optional if secret already exists in SM
```

Store the key in Secret Manager as a **raw string** (not JSON).

## Local / agent (optional)

```bash
uv sync --extra agent
export LANGSMITH_API_KEY=...          # or LANGCHAIN_API_KEY
export LANGCHAIN_PROJECT=olist-ml-agent
```

Agent review returns a `langsmith` status block when keyed.

## Local evals (always)

```bash
make agent-evals
# → artifacts/agent_eval_report.json
```

Deterministic policy-compliance checks live under `evals/` (must be 0 failures).
