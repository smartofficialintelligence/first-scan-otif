"""Target construction for promise-miss at carrier handoff (ADR 0006)."""

from __future__ import annotations

import pandas as pd

from olist_ml.logging import get_logger

logger = get_logger(__name__)

# Diagnostic duration SLA (not the training objective).
LONG_DELIVERY_THRESHOLD_DAYS: float = 14.0

ORDER_TS_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def _parse_timestamps(orders: pd.DataFrame) -> pd.DataFrame:
    out = orders.copy()
    for col in ORDER_TS_COLS:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce", utc=True)
    return out


def build_labeled_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """
    Build handoff timestamp + promise_miss label.

    prediction_ts = order_approved_at ?? order_purchase_timestamp  (approval clock)
    handoff_ts    = order_delivered_carrier_date                   (decision moment)
    promise_miss  = order_delivered_customer_date > order_estimated_delivery_date

    Customer delivery is label-only. long_delivery (>14d from approval) is retained
    as a diagnostic / PIT history rate source, not the training target.
    """
    df = _parse_timestamps(orders)
    df["prediction_ts"] = df["order_approved_at"].fillna(df["order_purchase_timestamp"])
    df["handoff_ts"] = df["order_delivered_carrier_date"]

    delivered = df["order_delivered_customer_date"].notna()
    estimated = df["order_estimated_delivery_date"].notna()
    has_pred = df["prediction_ts"].notna()
    has_handoff = df["handoff_ts"].notna()
    eligible = delivered & estimated & has_pred & has_handoff

    labeled = df.loc[eligible].copy()
    labeled["delivery_days"] = (
        labeled["order_delivered_customer_date"] - labeled["prediction_ts"]
    ).dt.total_seconds() / 86400.0
    labeled["long_delivery"] = (labeled["delivery_days"] > LONG_DELIVERY_THRESHOLD_DAYS).astype(int)
    labeled["promise_miss"] = (
        labeled["order_delivered_customer_date"] > labeled["order_estimated_delivery_date"]
    ).astype(int)
    labeled["estimated_delivery_horizon_days"] = (
        labeled["order_estimated_delivery_date"] - labeled["prediction_ts"]
    ).dt.total_seconds() / 86400.0

    dropped = len(df) - len(labeled)
    logger.info(
        "Labeled orders: %s eligible (dropped %s); promise_miss rate=%.3f "
        "(long_delivery>%.0fd rate=%.3f)",
        f"{len(labeled):,}",
        f"{dropped:,}",
        labeled["promise_miss"].mean() if len(labeled) else 0.0,
        LONG_DELIVERY_THRESHOLD_DAYS,
        labeled["long_delivery"].mean() if len(labeled) else 0.0,
    )
    return labeled.reset_index(drop=True)
