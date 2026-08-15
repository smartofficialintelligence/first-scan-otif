"""Assemble model matrices with consistent encoding for train and serve."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

from olist_ml.features.contracts import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES
from olist_ml.schemas import PredictRequest


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
        # Defaults for optional historical features in local mode.
        for key in [
            "seller_order_count_7d",
            "seller_order_count_30d",
            "seller_order_count_90d",
            "seller_late_rate_7d",
            "seller_late_rate_30d",
            "seller_late_rate_90d",
        ]:
            if row.get(key) is None:
                row[key] = 0.0
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
