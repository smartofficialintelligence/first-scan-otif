"""Model train/infer contract tests on fixtures."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from olist_ml.config import Settings
from olist_ml.features.assembler import select_feature_frame
from olist_ml.inference.predictor import PredictionService
from olist_ml.schemas import PredictRequest
from olist_ml.training.pipeline import run_training

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def test_train_and_deterministic_predict(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=FIXTURES,
        artifact_dir=tmp_path / "artifacts",
        model_path=tmp_path / "artifacts" / "model.joblib",
        model_meta_path=tmp_path / "artifacts" / "model_meta.json",
        n_optuna_trials=2,
        cv_folds=2,
        random_seed=42,
    )
    meta = run_training(settings, data_dir=FIXTURES)
    assert meta.model_version
    assert "test_pr_auc" in meta.metrics

    service = PredictionService(settings)
    service.load()
    assert service.ready

    # Build a request from a fixture feature row for realism
    from olist_ml.data.loaders import load_olist_tables
    from olist_ml.data.targets import build_labeled_orders
    from olist_ml.features.build import build_feature_table

    tables = load_olist_tables(FIXTURES)
    feats = build_feature_table(tables, build_labeled_orders(tables["orders"]))
    row = feats.iloc[-1]
    req = PredictRequest(
        order_id=str(row["order_id"]),
        seller_id=str(row["seller_id"]),
        purchase_timestamp=row["prediction_ts"].to_pydatetime(),
        prediction_timestamp=row["prediction_ts"].to_pydatetime(),
        item_count=int(row["item_count"]),
        basket_value=float(row["basket_value"]),
        freight_value=float(row["freight_value"]),
        seller_count=int(row["seller_count"]),
        category_count=int(row["category_count"]),
        payment_type_primary=str(row["payment_type_primary"]),
        installment_count=int(row["installment_count"]),
        estimated_delivery_horizon_days=float(row["estimated_delivery_horizon_days"]),
        customer_state=str(row["customer_state"]),
        seller_state_primary=str(row["seller_state_primary"]),
        geo_distance_km=float(row["geo_distance_km"]),
        approval_lag_hours=float(row["approval_lag_hours"]),
        same_state=float(row["same_state"]),
        avg_product_weight_g=float(row["avg_product_weight_g"]),
        freight_to_basket_ratio=float(row["freight_to_basket_ratio"]),
        primary_category=str(row["primary_category"]),
        seller_order_count_7d=float(row["seller_order_count_7d"]),
        seller_order_count_30d=float(row["seller_order_count_30d"]),
        seller_order_count_90d=float(row["seller_order_count_90d"]),
        seller_late_rate_7d=float(row["seller_late_rate_7d"]),
        seller_late_rate_30d=float(row["seller_late_rate_30d"]),
        seller_late_rate_90d=float(row["seller_late_rate_90d"]),
        seller_avg_freight_30d=float(row["seller_avg_freight_30d"]),
        seller_avg_freight_90d=float(row["seller_avg_freight_90d"]),
        seller_avg_basket_30d=float(row["seller_avg_basket_30d"]),
        seller_avg_basket_90d=float(row["seller_avg_basket_90d"]),
        customer_order_count_30d=float(row["customer_order_count_30d"]),
        customer_order_count_90d=float(row["customer_order_count_90d"]),
        customer_late_rate_90d=float(row["customer_late_rate_90d"]),
        category_late_rate_30d=float(row["category_late_rate_30d"]),
        category_late_rate_90d=float(row["category_late_rate_90d"]),
        remaining_to_promise_days=float(row["remaining_to_promise_days"]),
        handling_days=float(row["handling_days"]),
        handling_frac_of_promise=float(row["handling_frac_of_promise"]),
        limit_miss=float(row["limit_miss"]),
        category_order_count_90d=float(row["category_order_count_90d"]),
    )
    a = service.predict_one(req)
    b = service.predict_one(req)
    assert a.promise_miss_probability == b.promise_miss_probability
    assert 0.0 <= a.promise_miss_probability <= 1.0
    assert a.model_version == meta.model_version
    assert a.risk_band in {"low", "medium", "high"}

    # Feature matrix used in training must match contract width after encoding
    X = select_feature_frame(feats)
    proba = service._model.predict_proba(X)  # noqa: SLF001
    assert proba.shape[0] == len(X)
    assert np.all((proba[:, 1] >= 0) & (proba[:, 1] <= 1))
