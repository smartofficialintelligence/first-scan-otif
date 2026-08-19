"""App-level API key gates REST and MCP (probes stay open)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from olist_ml.config import Settings


def test_api_key_gates_metrics_and_mcp() -> None:
    import olist_ml.api.dependencies as deps
    from olist_ml.api.app import create_app

    deps.settings_dep.cache_clear()
    deps.prediction_service_dep.cache_clear()
    deps.decision_service_dep.cache_clear()
    deps.action_executor_dep.cache_clear()
    deps.decision_ledger_dep.cache_clear()

    settings = Settings(auth_mode="api_key", api_key="secret-key")
    app = create_app()
    app.dependency_overrides[deps.settings_dep] = lambda: settings
    headers = {"x-api-key": "secret-key"}
    mcp_headers = {
        **headers,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"},
        },
    }
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        assert client.get("/v1/metrics").status_code == 401
        blocked = client.post("/mcp", json=init_body, headers={"Accept": "application/json, text/event-stream"})
        assert blocked.status_code == 401
        assert client.get("/v1/metrics", headers=headers).status_code == 200
        allowed = client.post("/mcp", json=init_body, headers=mcp_headers)
        assert allowed.status_code == 200
