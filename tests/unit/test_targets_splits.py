"""Unit tests for target construction and temporal splits."""

from __future__ import annotations

import pandas as pd

from olist_ml.data.splits import temporal_split
from olist_ml.data.targets import LONG_DELIVERY_THRESHOLD_DAYS, build_labeled_orders
from olist_ml.inference.predictor import risk_band


def test_promise_miss_handoff_label_and_prediction_ts_fallback() -> None:
    orders = pd.DataFrame(
        [
            {
                "order_id": "a",
                "order_purchase_timestamp": "2018-01-01T10:00:00",
                "order_approved_at": None,
                "order_delivered_carrier_date": "2018-01-02T10:00:00",
                "order_delivered_customer_date": "2018-01-20T10:00:00",
                "order_estimated_delivery_date": "2018-01-15T00:00:00",
            },
            {
                "order_id": "b",
                "order_purchase_timestamp": "2018-01-01T10:00:00",
                "order_approved_at": "2018-01-01T12:00:00",
                "order_delivered_carrier_date": "2018-01-02T12:00:00",
                "order_delivered_customer_date": "2018-01-05T10:00:00",
                "order_estimated_delivery_date": "2018-01-20T00:00:00",
            },
            {
                "order_id": "c",
                "order_purchase_timestamp": "2018-01-01T10:00:00",
                "order_approved_at": "2018-01-01T12:00:00",
                "order_delivered_carrier_date": "2018-01-02T12:00:00",
                "order_delivered_customer_date": None,
                "order_estimated_delivery_date": "2018-01-05T00:00:00",
            },
            {
                "order_id": "d",
                "order_purchase_timestamp": "2018-01-01T10:00:00",
                "order_approved_at": "2018-01-01T12:00:00",
                "order_delivered_carrier_date": None,
                "order_delivered_customer_date": "2018-01-20T10:00:00",
                "order_estimated_delivery_date": "2018-01-15T00:00:00",
            },
        ]
    )
    labeled = build_labeled_orders(orders)
    assert set(labeled["order_id"]) == {"a", "b"}
    miss = labeled.set_index("order_id")["promise_miss"].to_dict()
    assert miss["a"] == 1
    assert miss["b"] == 0
    assert "handoff_ts" in labeled.columns
    assert LONG_DELIVERY_THRESHOLD_DAYS == 14.0
    row_a = labeled.set_index("order_id").loc["a"]
    assert row_a["prediction_ts"] == pd.Timestamp("2018-01-01T10:00:00", tz="UTC")
    assert row_a["handoff_ts"] == pd.Timestamp("2018-01-02T10:00:00", tz="UTC")


def test_temporal_split_is_chronological() -> None:
    frame = pd.DataFrame(
        {
            "handoff_ts": pd.date_range("2018-01-01", periods=100, freq="D", tz="UTC"),
            "promise_miss": [i % 4 == 0 for i in range(100)],
        }
    )
    splits = temporal_split(
        frame, time_col="handoff_ts", valid_fraction=0.15, test_fraction=0.15, replay_fraction=0.10
    )
    assert splits.train["handoff_ts"].max() <= splits.validation["handoff_ts"].min()
    assert splits.validation["handoff_ts"].max() <= splits.test["handoff_ts"].min()
    assert splits.test["handoff_ts"].max() <= splits.replay_holdout["handoff_ts"].min()
    total = (
        len(splits.train) + len(splits.validation) + len(splits.test) + len(splits.replay_holdout)
    )
    assert total == 100


def test_risk_band_thresholds() -> None:
    assert risk_band(0.1, low_max=0.3, medium_max=0.6) == "low"
    assert risk_band(0.45, low_max=0.3, medium_max=0.6) == "medium"
    assert risk_band(0.9, low_max=0.3, medium_max=0.6) == "high"


def test_blocked_columns_constant() -> None:
    from olist_ml.features.contracts import BLOCKED_SOURCE_COLUMNS

    assert "order_delivered_customer_date" in BLOCKED_SOURCE_COLUMNS
    assert "order_delivered_carrier_date" in BLOCKED_SOURCE_COLUMNS
    assert "review_score" in BLOCKED_SOURCE_COLUMNS
    from olist_ml.features.contracts import FEATURE_COLUMNS

    assert set(BLOCKED_SOURCE_COLUMNS).isdisjoint(FEATURE_COLUMNS)
