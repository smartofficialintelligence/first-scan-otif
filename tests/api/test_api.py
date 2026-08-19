"""API contract tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from olist_ml.config import Settings
from olist_ml.training.pipeline import run_training

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


@pytest.fixture(scope="module")
def trained_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    root = tmp_path_factory.mktemp("api-artifacts")
    settings = Settings(
        data_dir=FIXTURES,
        artifact_dir=root,
        model_path=root / "model.joblib",
        model_meta_path=root / "model_meta.json",
        decision_ledger_path=root / "decision_ledger.jsonl",
        n_optuna_trials=2,
        cv_folds=2,
        auth_mode="off",
    )
    run_training(settings, data_dir=FIXTURES)
    return settings


@pytest.fixture()
def client(trained_settings: Settings) -> TestClient:
    def _settings() -> Settings:
        return trained_settings

    import olist_ml.api.dependencies as deps
    from olist_ml.actions.executor import ActionExecutor
    from olist_ml.api.app import create_app
    from olist_ml.decisions.service import DecisionService
    from olist_ml.inference.predictor import PredictionService
    from olist_ml.outcomes.ledger import DecisionLedger

    deps.settings_dep.cache_clear()
    deps.prediction_service_dep.cache_clear()
    deps.decision_service_dep.cache_clear()
    deps.action_executor_dep.cache_clear()
    deps.decision_ledger_dep.cache_clear()

    service = PredictionService(trained_settings)
    service.load()
    decision_svc = DecisionService(config_path=trained_settings.policy_economics_path)
    executor = ActionExecutor(
        config_path=trained_settings.policy_economics_path,
        base_seed=trained_settings.decision_base_seed,
    )
    ledger = DecisionLedger(trained_settings.decision_ledger_path)

    app = create_app()
    app.dependency_overrides[deps.settings_dep] = _settings
    app.dependency_overrides[deps.prediction_service_dep] = lambda: service
    app.dependency_overrides[deps.decision_service_dep] = lambda: decision_svc
    app.dependency_overrides[deps.action_executor_dep] = lambda: executor
    app.dependency_overrides[deps.decision_ledger_dep] = lambda: ledger
    with TestClient(app) as test_client:
        yield test_client


def test_health_ready_predict(client: TestClient) -> None:
    from olist_ml.monitoring.metrics import get_metrics

    get_metrics().reset()
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready").json()
    assert ready["ready"] is True
    assert "service" in client.get("/v1/metrics").json()
    payload = {
        "order_id": "demo",
        "seller_id": "s000",
        "purchase_timestamp": datetime(2018, 2, 10, 12, 0, tzinfo=UTC).isoformat(),
        "prediction_timestamp": datetime(2018, 2, 10, 12, 0, tzinfo=UTC).isoformat(),
        "item_count": 2,
        "basket_value": 120.0,
        "freight_value": 15.0,
        "seller_count": 1,
        "category_count": 1,
        "payment_type_primary": "credit_card",
        "installment_count": 1,
        "estimated_delivery_horizon_days": 5.0,
        "customer_state": "SP",
        "seller_state_primary": "RJ",
        "geo_distance_km": 100.0,
        "seller_order_count_30d": 3,
        "seller_late_rate_30d": 0.2,
    }
    resp = client.post("/v1/predict", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["order_id"] == "demo"
    assert "prediction_id" in body
    assert body["prediction_id"]
    assert 0.0 <= body["promise_miss_probability"] <= 1.0
    assert body["target"] == "promise_miss_at_handoff"
    assert "model_version" in body


def test_explain(client: TestClient) -> None:
    payload = {
        "order_id": "demo",
        "seller_id": "s000",
        "purchase_timestamp": datetime(2018, 2, 10, 12, 0, tzinfo=UTC).isoformat(),
        "prediction_timestamp": datetime(2018, 2, 10, 12, 0, tzinfo=UTC).isoformat(),
        "item_count": 2,
        "basket_value": 120.0,
        "freight_value": 15.0,
        "seller_count": 1,
        "category_count": 1,
        "payment_type_primary": "credit_card",
        "installment_count": 1,
        "estimated_delivery_horizon_days": 5.0,
        "customer_state": "SP",
        "seller_state_primary": "RJ",
        "geo_distance_km": 100.0,
        "seller_order_count_30d": 3,
        "seller_late_rate_30d": 0.2,
    }
    resp = client.post("/v1/explain", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["order_id"] == "demo"
    assert body["method"] == "shap"
    assert "top_features" in body
    assert len(body["top_features"]) >= 1
    assert body["model_version"]
    assert "calibrat" in (body.get("note") or "").lower()


def test_invalid_payload(client: TestClient) -> None:
    resp = client.post("/v1/predict", json={"order_id": "x"})
    assert resp.status_code == 422


def _predict_payload(order_id: str = "demo") -> dict:
    return {
        "order_id": order_id,
        "seller_id": "s000",
        "purchase_timestamp": datetime(2018, 2, 10, 12, 0, tzinfo=UTC).isoformat(),
        "prediction_timestamp": datetime(2018, 2, 10, 12, 0, tzinfo=UTC).isoformat(),
        "item_count": 2,
        "basket_value": 180.0,
        "freight_value": 15.0,
        "seller_count": 1,
        "category_count": 1,
        "payment_type_primary": "credit_card",
        "installment_count": 1,
        "estimated_delivery_horizon_days": 5.0,
        "customer_state": "SP",
        "seller_state_primary": "RJ",
        "geo_distance_km": 100.0,
        "seller_order_count_30d": 3,
        "seller_late_rate_30d": 0.5,
    }


def test_decision_and_policy_endpoints(client: TestClient) -> None:
    policy = client.get("/v1/policies/current")
    assert policy.status_code == 200
    body = policy.json()
    assert body["policy_version"] == "noc-handoff-policy-v1"
    assert body["economics_gate"]["status"] == "approved"
    assert body["simulation_claims_allowed"] is True
    assert body["causal_roi_claim_allowed"] is False

    resp = client.post("/v1/decision", json={**_predict_payload("d1"), "simulate": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "prediction" in body and "decision" in body
    assert body["prediction"]["prediction_id"]
    assert body["decision"]["recommended_action"]
    assert "alternative_actions" in body["decision"]

    hist = client.get("/v1/orders/d1/decision")
    assert hist.status_code == 200
    assert len(hist.json()["records"]) >= 2


def test_decision_with_simulate(client: TestClient) -> None:
    resp = client.post(
        "/v1/decision",
        json={**_predict_payload("d2"), "simulate": True, "observed_promise_miss": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "action" in body
    assert body["action"]["status"] == "simulated"
    assert "observed_promise_miss" in body["action"]
    assert "simulated_promise_miss" in body["action"]

    action_id = body["action"]["action_id"]
    lookup = client.get(f"/v1/actions/{action_id}")
    assert lookup.status_code == 200
    assert lookup.json()["records"]
    missing = client.get("/v1/actions/does-not-exist")
    assert missing.status_code == 404


def test_agent_review_endpoint(client: TestClient) -> None:
    pred = client.post("/v1/predict", json=_predict_payload("agent-api")).json()
    resp = client.post(
        "/v1/agent/review",
        json={
            "order_id": pred["order_id"],
            "prediction_id": pred["prediction_id"],
            "model_version": pred["model_version"],
            "promise_miss_probability": pred["promise_miss_probability"],
            "remaining_to_promise_days": 4.0,
            "geo_distance_km": 200.0,
            "same_state": 0.0,
            "freight_value": 20.0,
            "basket_value": 250.0,
            "run_simulation": False,
            "require_human_approval": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["selected_action"]
    assert isinstance(body["tool_trace"], list)
    metrics = client.get("/v1/metrics").json()
    assert metrics["decision"]["agent_reviews"] >= 1


def _mcp_jsonrpc(response) -> dict:
    """Parse Streamable HTTP (JSON or SSE) into a JSON-RPC object."""
    ctype = response.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                if isinstance(payload, dict) and ("result" in payload or "error" in payload):
                    return payload
        raise AssertionError(response.text)
    return response.json()


def test_mcp_http_initialize_status_and_tools(client: TestClient) -> None:
    pytest.importorskip("mcp")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    init = client.post(
        "/mcp",
        headers=headers,
        follow_redirects=False,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        },
    )
    assert init.status_code == 200, init.text
    info = _mcp_jsonrpc(init)
    assert info["result"]["serverInfo"]["name"] == "olist-ml"

    listed = client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert listed.status_code == 200, listed.text
    tools = {t["name"] for t in _mcp_jsonrpc(listed)["result"]["tools"]}
    assert "get_model_status" in tools
    assert "predict_promise_miss" in tools
    assert "recommend_policy_action" in tools

    status = client.post(
        "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_model_status", "arguments": {}},
        },
    )
    assert status.status_code == 200, status.text
    result = _mcp_jsonrpc(status)["result"]
    # MCP tool results are text content wrapping JSON from the handler.
    text = "".join(part.get("text", "") for part in result.get("content", []) if part.get("type") == "text")
    body = json.loads(text)
    assert body["ready"] is True
    assert body["model_version"]
