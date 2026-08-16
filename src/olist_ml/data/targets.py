"""Target construction for long-delivery risk (H1 amended)."""

from __future__ import annotations

import pandas as pd

from olist_ml.logging import get_logger

logger = get_logger(__name__)

# Fixed operational SLA used as the positive class (days from prediction_ts).
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
    Build prediction timestamp + long_delivery label.

    prediction_ts = order_approved_at ?? order_purchase_timestamp
    delivery_days = order_delivered_customer_date - prediction_ts
    long_delivery = delivery_days > LONG_DELIVERY_THRESHOLD_DAYS

    Also retains promise_miss (delivered after estimated date) as a diagnostic column only.
    """
    df = _parse_timestamps(orders)
    df["prediction_ts"] = df["order_approved_at"].fillna(df["order_purchase_timestamp"])

    delivered = df["order_delivered_customer_date"].notna()
    estimated = df["order_estimated_delivery_date"].notna()
    has_pred = df["prediction_ts"].notna()
    eligible = delivered & estimated & has_pred

    labeled = df.loc[eligible].copy()
    labeled["delivery_days"] = (
        labeled["order_delivered_customer_date"] - labeled["prediction_ts"]
    ).dt.total_seconds() / 86400.0
    labeled["long_delivery"] = (labeled["delivery_days"] > LONG_DELIVERY_THRESHOLD_DAYS).astype(int)
    # Diagnostic / legacy: miss vs customer-facing estimate (weak signal on Olist).
    labeled["promise_miss"] = (
        labeled["order_delivered_customer_date"] > labeled["order_estimated_delivery_date"]
    ).astype(int)
    labeled["estimated_delivery_horizon_days"] = (
        labeled["order_estimated_delivery_date"] - labeled["prediction_ts"]
    ).dt.total_seconds() / 86400.0

    dropped = len(df) - len(labeled)
    logger.info(
        "Labeled orders: %s eligible (dropped %s); long_delivery(>%.0fd) rate=%.3f "
        "(promise_miss rate=%.3f)",
        f"{len(labeled):,}",
        f"{dropped:,}",
        LONG_DELIVERY_THRESHOLD_DAYS,
        labeled["long_delivery"].mean() if len(labeled) else 0.0,
        labeled["promise_miss"].mean() if len(labeled) else 0.0,
    )
    return labeled.reset_index(drop=True)
