# Milestone 6 / D7 — MCP

Agent tools call the same domain services as REST — no duplicated inference or policy logic.

## Install

```bash
uv sync --extra mcp
# or: uv sync --all-extras
```

## Prediction tools

| Tool | Maps to |
|------|---------|
| `predict_long_delivery` | `PredictionService.predict_one` |
| `get_order_risk` | same as `predict_long_delivery` (agent-friendly name) |
| `get_model_status` | `PredictionService.readiness` |
| `get_model_metrics` | `PredictionService.model_info` |
| `explain_long_delivery` | `PredictionService.explain_one` |

## Decision tools (D7)

| Tool | Maps to |
|------|---------|
| `list_available_actions` | policy economics config |
| `calculate_action_value` | EV scoring for one action |
| `recommend_policy_action` | predict → `DecisionService` (same as `POST /v1/decision`) |
| `execute_simulated_action` | `ActionExecutor` (simulation only) |
| `get_action_outcome` | local decision ledger by `action_id` |
| `get_decision_history` | local decision ledger by `order_id` |
| `get_policy_metrics` | current policy version + economics |

Intervention effectiveness values are **simulation assumptions**, not causal estimates.

Predict/recommend args mirror `PredictRequest` fields (timestamps as ISO-8601 strings).

## Run

```bash
make mcp-serve
# or: uv run olist-mcp
```

Uses `mcp.server.mcpserver.MCPServer` (stdio transport). Entry point: `olist-mcp`.

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
uv run pytest tests/api/test_mcp_tools.py tests/api/test_mcp_decision_tools.py -q
```
