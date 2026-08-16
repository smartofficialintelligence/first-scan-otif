"""Unit tests for target construction and temporal splits."""

from __future__ import annotations

import pandas as pd

from olist_ml.data.splits import temporal_split
from olist_ml.data.targets import LONG_DELIVERY_THRESHOLD_DAYS, build_labeled_orders
from olist_ml.inference.predictor import risk_band


def test_long_delivery_target_and_prediction_ts_fallback() -> None:
    orders = pd.DataFrame(
        [
            {
                "order_id": "a",
                "order_purchase_timestamp": "2018-01-01T10:00:00",
                "order_approved_at": None,
                "order_delivered_customer_date": "2018-01-20T10:00:00",  # 19d from purchase
                "order_estimated_delivery_date": "2018-01-15T00:00:00",
            },
            {
                "order_id": "b",
                "order_purchase_timestamp": "2018-01-01T10:00:00",
                "order_approved_at": "2018-01-01T12:00:00",
                "order_delivered_customer_date": "2018-01-05T10:00:00",  # ~4d
                "order_estimated_delivery_date": "2018-01-20T00:00:00",
            },
            {
                "order_id": "c",
                "order_purchase_timestamp": "2018-01-01T10:00:00",
                "order_approved_at": "2018-01-01T12:00:00",
                "order_delivered_customer_date": None,
                "order_estimated_delivery_date": "2018-01-05T00:00:00",
            },
        ]
    )
    labeled = build_labeled_orders(orders)
    assert set(labeled["order_id"]) == {"a", "b"}
    long = labeled.set_index("order_id")["long_delivery"].to_dict()
    assert long["a"] == 1
    assert long["b"] == 0
    assert LONG_DELIVERY_THRESHOLD_DAYS == 14.0
    # fallback to purchase when approval null
    row_a = labeled.set_index("order_id").loc["a"]
    assert row_a["prediction_ts"] == pd.Timestamp("2018-01-01T10:00:00", tz="UTC")


def test_temporal_split_is_chronological() -> None:
    frame = pd.DataFrame(
        {
            "prediction_ts": pd.date_range("2018-01-01", periods=100, freq="D", tz="UTC"),
            "long_delivery": [i % 4 == 0 for i in range(100)],
        }
    )
    splits = temporal_split(frame, valid_fraction=0.15, test_fraction=0.15, replay_fraction=0.10)
    assert splits.train["prediction_ts"].max() <= splits.validation["prediction_ts"].min()
    assert splits.validation["prediction_ts"].max() <= splits.test["prediction_ts"].min()
    assert splits.test["prediction_ts"].max() <= splits.replay_holdout["prediction_ts"].min()
    total = (
        len(splits.train)
        + len(splits.validation)
        + len(splits.test)
        + len(splits.replay_holdout)
    )
    assert total == 100


def test_risk_band_thresholds() -> None:
    assert risk_band(0.1, low_max=0.3, medium_max=0.6) == "low"
    assert risk_band(0.45, low_max=0.3, medium_max=0.6) == "medium"
    assert risk_band(0.9, low_max=0.3, medium_max=0.6) == "high"


def test_blocked_columns_constant() -> None:
    from olist_ml.features.contracts import BLOCKED_SOURCE_COLUMNS

    assert "order_delivered_customer_date" in BLOCKED_SOURCE_COLUMNS
    assert "review_score" in BLOCKED_SOURCE_COLUMNS
