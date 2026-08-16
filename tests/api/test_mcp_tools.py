"""Unit tests for MCP tool handlers (PredictionService only — no duplicated logic)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from olist_ml.api import mcp_server
from olist_ml.config import Settings
from olist_ml.inference.predictor import PredictionService
from olist_ml.training.pipeline import run_training

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


@pytest.fixture(scope="module")
def trained_service(tmp_path_factory: pytest.TempPathFactory) -> PredictionService:
    root = tmp_path_factory.mktemp("mcp-artifacts")
    settings = Settings(
        data_dir=FIXTURES,
        artifact_dir=root,
        model_path=root / "model.joblib",
        model_meta_path=root / "model_meta.json",
        n_optuna_trials=2,
        cv_folds=2,
        auth_mode="off",
    )
    run_training(settings, data_dir=FIXTURES)
    service = PredictionService(settings)
    service.load()
    return service


@pytest.fixture(autouse=True)
def _inject_service(trained_service: PredictionService):
    mcp_server.set_service(trained_service)
    yield
    mcp_server.set_service(trained_service)  # keep module fixture available


def _payload() -> dict:
    ts = datetime(2018, 2, 10, 12, 0, tzinfo=UTC).isoformat()
    return {
        "order_id": "mcp-demo",
        "seller_id": "s000",
        "purchase_timestamp": ts,
        "prediction_timestamp": ts,
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
        "seller_order_count_30d": 3.0,
        "seller_late_rate_30d": 0.2,
    }


def test_get_model_status(trained_service: PredictionService) -> None:
    status = mcp_server.get_model_status(service=trained_service)
    assert status["ready"] is True
    assert status["model_version"]


def test_get_model_metrics(trained_service: PredictionService) -> None:
    info = mcp_server.get_model_metrics(service=trained_service)
    assert info["ready"] is True
    assert isinstance(info["feature_names"], list)
    assert len(info["feature_names"]) > 0


def test_predict_long_delivery(trained_service: PredictionService) -> None:
    body = mcp_server.predict_long_delivery(service=trained_service, **_payload())
    assert body["order_id"] == "mcp-demo"
    assert 0.0 <= body["long_delivery_probability"] <= 1.0
    assert "model_version" in body


def test_explain_long_delivery(trained_service: PredictionService) -> None:
    body = mcp_server.explain_long_delivery(service=trained_service, **_payload())
    assert body["order_id"] == "mcp-demo"
    assert body["method"] == "stub"
    assert "top_features" in body
    assert isinstance(body["top_features"], list)
    assert body["top_features"]
    assert body["top_features"][0]["contribution"] == 0.0
