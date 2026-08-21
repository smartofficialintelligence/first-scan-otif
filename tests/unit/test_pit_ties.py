"""Point-in-time windows must exclude events sharing the current timestamp.

Regression test for a real bug: the window cut used the row's positional index
instead of the first row carrying the same timestamp, so when a seller had two
orders scanned in the same instant, the second counted the first as history.
That contradicted ARCHITECTURE §3 ("events strictly before handoff_ts") and put
the pandas builder 1 count ahead of the dbt marts on 9,937 of 96,475 rows.
"""

from __future__ import annotations

import pandas as pd

from olist_ml.features.build import _pit_window_stats

WINDOWS = {"7d": 7, "30d": 30, "90d": 90}


def _stats(df: pd.DataFrame) -> pd.DataFrame:
    return _pit_window_stats(
        df,
        entity_col="seller_id",
        time_col="handoff_ts",
        windows_days=WINDOWS,
        count_prefix="seller_order_count",
        rate_prefix="seller_late_rate",
        rate_source="long_delivery",
        observed_at_col="order_delivered_customer_date",
    )


def test_tied_timestamps_are_not_counted_as_history():
    """Two orders scanned in the same instant are not each other's priors."""
    ts = pd.Timestamp("2018-03-01", tz="UTC")
    df = pd.DataFrame(
        {
            "seller_id": ["s1", "s1"],
            "handoff_ts": [ts, ts],
            "long_delivery": [1, 1],
            "order_delivered_customer_date": [pd.NaT, pd.NaT],
        }
    )
    out = _stats(df)
    # Neither row may see the other, regardless of ordering.
    assert out["seller_order_count_90d"].tolist() == [0.0, 0.0]


def test_earlier_orders_still_count():
    """The fix must not throw away genuine history."""
    df = pd.DataFrame(
        {
            "seller_id": ["s1", "s1", "s1"],
            "handoff_ts": pd.to_datetime(
                ["2018-03-01", "2018-03-05", "2018-03-05"], utc=True
            ),
            "long_delivery": [1, 0, 0],
            "order_delivered_customer_date": [
                pd.Timestamp("2018-03-02", tz="UTC"),
                pd.NaT,
                pd.NaT,
            ],
        }
    )
    out = _stats(df).sort_index()
    counts = out["seller_order_count_90d"].tolist()
    # First order: no history. The two tied later orders each see only the
    # first order — one prior each, never two, and never each other.
    assert counts == [0.0, 1.0, 1.0]


def test_tie_group_of_three_sees_only_earlier_events():
    ts = pd.Timestamp("2018-06-01", tz="UTC")
    df = pd.DataFrame(
        {
            "seller_id": ["s1"] * 4,
            "handoff_ts": [pd.Timestamp("2018-05-30", tz="UTC"), ts, ts, ts],
            "long_delivery": [0, 0, 0, 0],
            "order_delivered_customer_date": [
                pd.Timestamp("2018-05-31", tz="UTC"),
                pd.NaT,
                pd.NaT,
                pd.NaT,
            ],
        }
    )
    out = _stats(df).sort_index()
    assert out["seller_order_count_90d"].tolist() == [0.0, 1.0, 1.0, 1.0]


def test_rates_ignore_tied_siblings_too():
    """The rate denominator uses the same window cut as the count."""
    ts = pd.Timestamp("2018-04-10", tz="UTC")
    df = pd.DataFrame(
        {
            "seller_id": ["s1", "s1"],
            "handoff_ts": [ts, ts],
            "long_delivery": [1, 1],
            # Delivered before the scan, so it would be "knowable" if counted.
            "order_delivered_customer_date": [
                pd.Timestamp("2018-04-01", tz="UTC"),
                pd.Timestamp("2018-04-01", tz="UTC"),
            ],
        }
    )
    out = _stats(df)
    # No priors at all => rate stays 0.0, not 1.0 from the tied twin.
    assert out["seller_late_rate_90d"].tolist() == [0.0, 0.0]
