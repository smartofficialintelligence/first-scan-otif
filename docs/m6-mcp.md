# Milestone 6 / D7 — MCP

Agent tools call the same domain services as REST — no duplicated inference or policy logic.

## Install

`mcp` is a core dependency (`uv sync`). The optional extra remains as an alias:

```bash
uv sync
# or: uv sync --extra mcp
```

## Prediction tools

| Tool | Maps to |
|------|---------|
| `predict_promise_miss` | `PredictionService.predict_one` |
| `get_order_risk` | same path (agent-friendly name); accepts handoff clocks |
| `get_model_status` | `PredictionService.readiness` |
| `get_model_metrics` | `PredictionService.model_info` |
| `explain_promise_miss` | `PredictionService.explain_one` (Tree SHAP, pre-calibration) |

Handoff clocks (`handling_days`, `remaining_to_promise_days`, `handling_frac_of_promise`, `limit_miss`, `same_state`) are optional tool args and flow into `PredictRequest`.

## Decision tools (D7)

| Tool | Maps to |
|------|---------|
| `list_available_actions` | policy economics config (`noc-handoff-policy-v1`) |
| `calculate_action_value` | simulation scoring (`promise_miss_probability`) |
| `recommend_policy_action` | predict → NOC `DecisionService` (same as `POST /v1/decision`) |
| `execute_simulated_action` | `ActionExecutor` (simulation only); `observed_promise_miss` |
| `get_action_outcome` | local decision ledger by `action_id` |
| `get_decision_history` | local decision ledger by `order_id` |
| `get_policy_metrics` | current policy version + economics |

Intervention effectiveness values are **simulation assumptions**, not causal estimates.

Predict/recommend args mirror `PredictRequest` fields (timestamps as ISO-8601 strings).

## Run

### Streamable HTTP (same process as REST)

`make serve-local` or Cloud Run (`make gcp-up`) mounts MCP at **`POST /mcp`**. Same `PredictionService` as `/v1/predict`. Cloud Run IAM is the auth gate (Bearer identity token), identical to REST.

```bash
make serve-local
# other terminal — initialize:
curl -s http://127.0.0.1:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

Cursor / Claude Desktop remote server (laptop, Cloud Run up):

```json
{
  "mcpServers": {
    "olist-ml": {
      "url": "https://olist-ml-api-xxxxx-uc.a.run.app/mcp",
      "headers": {
        "Authorization": "Bearer <gcloud auth print-identity-token>"
      }
    }
  }
}
```

User login tokens: `gcloud auth print-identity-token` with **no** `--audiences`. Tokens expire (~1h). Or proxy without a Bearer header:

```bash
gcloud run services proxy olist-ml-api --region=us-central1
# then url: http://127.0.0.1:8080/mcp
```

### stdio (local agents)

```bash
make mcp-serve
# or: uv run olist-mcp
```

Uses `mcp.server.mcpserver.MCPServer` (stdio transport). Entry point: `olist-mcp`. Keep this for local LangGraph / inspector wiring that speaks stdio.

## Agent review (D8+)

Bounded LangGraph workflow (optional extra `agent`) calls the same decision tools:

```bash
uv sync --extra agent
make demo-decision   # B/C/D/E/G scenarios → artifacts/demo_decision_chain.json
make agent-evals     # local policy-compliance cases (no LangSmith required)
```

REST: `POST /v1/agent/review` — tool-driven selection + optional human gate (`require_human_approval` / `human_approved`).

LangSmith (optional): [d9-langsmith.md](d9-langsmith.md). Economics gates: [h9-h10-economics-gate.md](h9-h10-economics-gate.md).

## Tests

```bash
uv run pytest tests/api/test_mcp_tools.py tests/api/test_mcp_decision_tools.py tests/api/test_api.py -q
```
