"""API contract tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from olist_ml.api.dependencies import prediction_service_dep, settings_dep
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
        n_optuna_trials=2,
        cv_folds=2,
        auth_mode="off",
    )
    run_training(settings, data_dir=FIXTURES)
    return settings


@pytest.fixture()
def client(trained_settings: Settings) -> TestClient:
    settings_dep.cache_clear()
    prediction_service_dep.cache_clear()

    def _settings() -> Settings:
        return trained_settings

    # Patch cached deps
    import olist_ml.api.dependencies as deps
    from olist_ml.api.app import create_app
    from olist_ml.inference.predictor import PredictionService

    deps.settings_dep.cache_clear()
    deps.prediction_service_dep.cache_clear()

    service = PredictionService(trained_settings)
    service.load()

    app = create_app()
    app.dependency_overrides[deps.settings_dep] = _settings
    app.dependency_overrides[deps.prediction_service_dep] = lambda: service
    return TestClient(app)


def test_health_ready_predict(client: TestClient) -> None:
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready").json()
    assert ready["ready"] is True
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
    assert 0.0 <= body["late_delivery_probability"] <= 1.0
    assert "model_version" in body


def test_invalid_payload(client: TestClient) -> None:
    resp = client.post("/v1/predict", json={"order_id": "x"})
    assert resp.status_code == 422
