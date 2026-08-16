# Milestone 6 — MCP

Agent tools call the same `PredictionService` as REST — no duplicated inference.

## Install

```bash
uv sync --extra mcp
# or: uv sync --all-extras
```

## Tools

| Tool | Maps to |
|------|---------|
| `predict_long_delivery` | `PredictionService.predict_one` |
| `get_model_status` | `PredictionService.readiness` |
| `get_model_metrics` | `PredictionService.model_info` |
| `explain_long_delivery` | `PredictionService.explain_one` (same stub as `/v1/explain`) |

Predict/explain args mirror `PredictRequest` fields (timestamps as ISO-8601 strings).

## Run

```bash
make mcp-serve
# or: uv run olist-mcp
```

Uses `mcp.server.mcpserver.MCPServer` (stdio transport). Entry point: `olist-mcp`.

## Tests

```bash
uv run pytest tests/api/test_mcp_tools.py -q
```

Handlers are unit-tested against a fixture-trained `PredictionService`.
