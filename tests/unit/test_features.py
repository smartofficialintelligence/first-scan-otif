"""Feature build and PIT seller history tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.build import build_feature_table
from olist_ml.features.contracts import FEATURE_COLUMNS

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def test_feature_table_has_contract_columns() -> None:
    tables = load_olist_tables(FIXTURES)
    labeled = build_labeled_orders(tables["orders"])
    feats = build_feature_table(tables, labeled)
    assert "promise_miss" in feats.columns
    assert "handoff_ts" in feats.columns
    for col in FEATURE_COLUMNS:
        assert col in feats.columns, col
    assert feats["seller_order_count_30d"].notna().all()
    # first chronological handoff for a seller should have zero history
    first = feats.sort_values("handoff_ts").groupby("seller_id").head(1)
    assert (first["seller_order_count_7d"] == 0).all()
    assert (first["seller_late_rate_30d"] == 0).all()
    assert (first["customer_order_count_90d"] == 0).all()


def test_seller_history_excludes_current_order() -> None:
    tables = load_olist_tables(FIXTURES)
    labeled = build_labeled_orders(tables["orders"])
    feats = build_feature_table(tables, labeled)
    # For each seller, count of prior orders within 90d should be < total seller orders
    for _seller_id, g in feats.groupby("seller_id"):
        g = g.sort_values("handoff_ts")
        if len(g) < 2:
            continue
        # last row history count should equal number of earlier rows in fixture window
        last = g.iloc[-1]
        assert last["seller_order_count_90d"] == float(len(g) - 1)


def test_late_rate_uses_only_observed_prior_outcomes() -> None:
    """A prior handoff whose delivery is after the current scan must not enter late_rate."""
    from olist_ml.features.build import _pit_window_stats

    frame = pd.DataFrame(
        {
            "seller_id": ["s", "s"],
            "handoff_ts": pd.to_datetime(
                ["2018-01-01T00:00:00Z", "2018-01-05T00:00:00Z"], utc=True
            ),
            "order_delivered_customer_date": pd.to_datetime(
                ["2018-01-20T00:00:00Z", "2018-01-10T00:00:00Z"], utc=True
            ),
            "long_delivery": [1, 0],
            "freight_value": [10.0, 10.0],
        }
    )
    stats = _pit_window_stats(
        frame,
        entity_col="seller_id",
        time_col="handoff_ts",
        windows_days={"90d": 90},
        count_prefix="seller_order_count",
        rate_prefix="seller_late_rate",
        mean_specs=None,
    )
    second = stats.set_index("_row").loc[1]
    assert second["seller_order_count_90d"] == 1.0
    assert second["seller_late_rate_90d"] == 0.0


def test_derived_order_features_present() -> None:
    tables = load_olist_tables(FIXTURES)
    labeled = build_labeled_orders(tables["orders"])
    feats = build_feature_table(tables, labeled)
    assert (feats["freight_to_basket_ratio"] >= 0).all()
    assert set(feats["same_state"].unique()).issubset({0.0, 1.0})
    assert feats["approval_lag_hours"].ge(0).all()
    assert feats["primary_category"].notna().all()
    assert "handling_days" in feats.columns
    assert "remaining_to_promise_days" in feats.columns
    assert "limit_miss" in feats.columns
    assert feats["handling_days"].ge(-1).all()
