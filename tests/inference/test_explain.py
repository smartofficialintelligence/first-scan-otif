"""Unit tests for Tree SHAP helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xgboost as xgb

from olist_ml.config import Settings
from olist_ml.inference.explain import (
    display_feature_name,
    tree_shap_top_features,
    unwrap_xgb_classifier,
)
from olist_ml.inference.predictor import PredictionService
from olist_ml.schemas import PredictRequest


def test_display_feature_name_strips_column_transformer_prefix() -> None:
    assert display_feature_name("num__remaining_to_promise_days") == "remaining_to_promise_days"
    assert display_feature_name("cat__customer_state_sp") == "customer_state_sp"
    assert display_feature_name("handling_days") == "handling_days"


def test_unwrap_xgb_from_calibrated_frozen() -> None:
    import xgboost as xgb

    tree = xgb.XGBClassifier()
    frozen = SimpleNamespace(estimator=tree)
    calibrated = SimpleNamespace(calibrated_classifiers_=[SimpleNamespace(estimator=frozen)])
    assert unwrap_xgb_classifier(calibrated) is tree
    assert unwrap_xgb_classifier(tree) is tree


def test_tree_shap_nonzero_on_separable_stump() -> None:
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0, 0.2, 40), rng.normal(3, 0.2, 40)]).reshape(-1, 1)
    y = np.array([0] * 40 + [1] * 40)
    clf = xgb.XGBClassifier(
        n_estimators=8,
        max_depth=2,
        learning_rate=0.5,
        verbosity=0,
        n_jobs=1,
        min_child_weight=1,
        gamma=0,
    )
    clf.fit(x, y)
    top, _ = tree_shap_top_features(clf, np.array([[3.0]], dtype=np.float32), ["x"], top_k=1)
    assert top[0].feature == "x"
    assert abs(top[0].contribution) > 0


@pytest.mark.skipif(
    not Path("artifacts/model.joblib").exists() or not Path("artifacts/model_meta.json").exists(),
    reason="champion artifact not present",
)
def test_explain_champion_has_nonzero_shap() -> None:
    settings = Settings(
        model_path=Path("artifacts/model.joblib"),
        model_meta_path=Path("artifacts/model_meta.json"),
    )
    service = PredictionService(settings)
    service.load()
    req = PredictRequest(
        order_id="shap-champ",
        seller_id="s",
        purchase_timestamp=datetime(2018, 7, 19, 8, 58, 48, tzinfo=UTC),
        prediction_timestamp=datetime(2018, 7, 19, 9, 10, 16, tzinfo=UTC),
        item_count=2,
        basket_value=280.0,
        freight_value=42.0,
        estimated_delivery_horizon_days=8.0,
        customer_state="SP",
        seller_state_primary="RJ",
        geo_distance_km=250.0,
        seller_late_rate_30d=0.35,
        handling_days=3.0,
        remaining_to_promise_days=4.0,
    )
    body = service.explain_one(req)
    assert body.method == "shap"
    assert any(abs(f.contribution) > 0 for f in body.top_features)
