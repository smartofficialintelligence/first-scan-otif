"""Assemble model matrices with consistent encoding for train and serve."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

from olist_ml.features.contracts import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES
from olist_ml.schemas import PredictRequest

# Optional request / Feast fields defaulted to 0 when absent (cold-start / local mode).
_OPTIONAL_NUMERIC_DEFAULTS: tuple[str, ...] = (
    "approval_lag_hours",
    "same_state",
    "avg_product_weight_g",
    "seller_order_count_7d",
    "seller_order_count_30d",
    "seller_order_count_90d",
    "seller_late_rate_7d",
    "seller_late_rate_30d",
    "seller_late_rate_90d",
    "seller_avg_freight_30d",
    "seller_avg_freight_90d",
    "seller_avg_basket_30d",
    "seller_avg_basket_90d",
    "customer_order_count_30d",
    "customer_order_count_90d",
    "customer_late_rate_90d",
    "category_late_rate_30d",
    "category_late_rate_90d",
    "category_order_count_90d",
)


@dataclass
class AssembledFeatures:
    X: np.ndarray
    feature_names: list[str]
    y: np.ndarray | None = None


def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", "passthrough", NUMERIC_FEATURES),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )


def frame_from_requests(requests: list[PredictRequest]) -> pd.DataFrame:
    rows = []
    for req in requests:
        row = req.model_dump()
        for key in _OPTIONAL_NUMERIC_DEFAULTS:
            if row.get(key) is None:
                row[key] = 0.0
        if not row.get("primary_category"):
            row["primary_category"] = "unknown"
        else:
            row["primary_category"] = str(row["primary_category"]).strip().lower()

        basket = float(row.get("basket_value") or 0.0)
        freight = float(row.get("freight_value") or 0.0)
        if row.get("freight_to_basket_ratio") is None:
            row["freight_to_basket_ratio"] = (freight / basket) if basket > 0 else 0.0

        cust = str(row.get("customer_state") or "unknown").lower()
        sell = str(row.get("seller_state_primary") or "unknown").lower()
        if row.get("same_state") is None:
            row["same_state"] = float(cust == sell and cust != "unknown")

        ts = req.prediction_timestamp or req.purchase_timestamp
        row["purchase_hour"] = float(ts.hour)
        row["purchase_dow"] = float(ts.weekday())
        row["purchase_month"] = float(ts.month)
        row["is_weekend"] = float(ts.weekday() >= 5)
        rows.append(row)
    return pd.DataFrame(rows)


def select_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")
    return df[FEATURE_COLUMNS].copy()
