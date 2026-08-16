# D9 — LangSmith tracing (optional)

Local agent evals do **not** require LangSmith. Cloud tracing is opt-in.

## Enable

```bash
uv sync --extra agent
export LANGSMITH_API_KEY=...          # or LANGCHAIN_API_KEY
export LANGCHAIN_PROJECT=olist-ml-agent   # optional
# unset or set LANGCHAIN_TRACING_V2=false to disable
```

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
