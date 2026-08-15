"""Offline feature builder for local Milestone 1 (PIT-safe)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from olist_ml.features.contracts import FEATURE_COLUMNS
from olist_ml.logging import get_logger

logger = get_logger(__name__)


def _haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    r = 6371.0
    phi1 = np.radians(lat1.astype(float))
    phi2 = np.radians(lat2.astype(float))
    dphi = np.radians(lat2.astype(float) - lat1.astype(float))
    dlambda = np.radians(lon2.astype(float) - lon1.astype(float))
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a.clip(0, 1)))


def _zip5(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)


def _geo_centroids(geolocation: pd.DataFrame) -> pd.DataFrame:
    geo = geolocation.copy()
    geo["geolocation_zip_code_prefix"] = _zip5(geo["geolocation_zip_code_prefix"])
    return geo.groupby("geolocation_zip_code_prefix", as_index=False).agg(
        lat=("geolocation_lat", "mean"),
        lng=("geolocation_lng", "mean"),
    )


def _order_level_basket(tables: dict[str, pd.DataFrame], labeled: pd.DataFrame) -> pd.DataFrame:
    items = tables["order_items"].copy()
    products = tables["products"][["product_id", "product_category_name"]].copy()
    items = items.merge(products, on="product_id", how="left")

    basket = items.groupby("order_id", as_index=False).agg(
        item_count=("order_item_id", "count"),
        basket_value=("price", "sum"),
        freight_value=("freight_value", "sum"),
        seller_count=("seller_id", "nunique"),
        category_count=("product_category_name", "nunique"),
        primary_seller_id=("seller_id", "first"),
    )

    payments = tables["payments"].copy()
    pay = (
        payments.sort_values(["order_id", "payment_value"], ascending=[True, False])
        .groupby("order_id", as_index=False)
        .agg(
            payment_type_primary=("payment_type", "first"),
            installment_count=("payment_installments", "max"),
        )
    )

    customers = tables["customers"][
        ["customer_id", "customer_state", "customer_zip_code_prefix"]
    ].copy()
    customers["customer_zip_code_prefix"] = _zip5(customers["customer_zip_code_prefix"])
    sellers = tables["sellers"][["seller_id", "seller_state", "seller_zip_code_prefix"]].rename(
        columns={"seller_id": "primary_seller_id", "seller_state": "seller_state_primary"}
    ).copy()
    sellers["seller_zip_code_prefix"] = _zip5(sellers["seller_zip_code_prefix"])

    geo = _geo_centroids(tables["geolocation"])
    cust = customers.merge(
        geo.rename(
            columns={
                "geolocation_zip_code_prefix": "customer_zip_code_prefix",
                "lat": "customer_lat",
                "lng": "customer_lng",
            }
        ),
        on="customer_zip_code_prefix",
        how="left",
    )
    sell = sellers.merge(
        geo.rename(
            columns={
                "geolocation_zip_code_prefix": "seller_zip_code_prefix",
                "lat": "seller_lat",
                "lng": "seller_lng",
            }
        ),
        on="seller_zip_code_prefix",
        how="left",
    )

    base = labeled.merge(basket, on="order_id", how="inner")
    base = base.merge(pay, on="order_id", how="left")
    base = base.merge(cust, on="customer_id", how="left")
    base = base.merge(sell, on="primary_seller_id", how="left")
    base["geo_distance_km"] = _haversine_km(
        base["customer_lat"], base["customer_lng"], base["seller_lat"], base["seller_lng"]
    ).fillna(0.0)
    base["seller_id"] = base["primary_seller_id"]
    return base


def _add_time_parts(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out["prediction_ts"], utc=True)
    out["purchase_hour"] = ts.dt.hour.astype(float)
    out["purchase_dow"] = ts.dt.dayofweek.astype(float)
    out["purchase_month"] = ts.dt.month.astype(float)
    out["is_weekend"] = (ts.dt.dayofweek >= 5).astype(float)
    return out


def _seller_history_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Point-in-time seller rolling counts/late rates.

    Uses expanding history strictly before each order (closed left) with
    time-window filters of 7/30/90 days.
    """
    work = df.sort_values(["seller_id", "prediction_ts"]).copy()
    work["_row"] = np.arange(len(work))

    windows = {"7d": 7, "30d": 30, "90d": 90}
    for suffix in windows:
        work[f"seller_order_count_{suffix}"] = 0.0
        work[f"seller_late_rate_{suffix}"] = 0.0

    records: list[dict[str, float | int]] = []
    for _, group in work.groupby("seller_id", sort=False):
        g = group.sort_values("prediction_ts")
        times = g["prediction_ts"].to_numpy()
        late = g["late_delivery"].to_numpy()
        rows = g["_row"].to_numpy()
        for i in range(len(g)):
            t = times[i]
            rec: dict[str, float | int] = {"_row": int(rows[i])}
            for suffix, days in windows.items():
                start = t - pd.Timedelta(days=days)
                # strictly before current order
                mask = (times < t) & (times >= start)
                count = int(mask.sum())
                rate = float(late[mask].mean()) if count else 0.0
                rec[f"seller_order_count_{suffix}"] = float(count)
                rec[f"seller_late_rate_{suffix}"] = rate
            records.append(rec)

    hist = pd.DataFrame.from_records(records)
    drop_cols = [
        c
        for c in work.columns
        if c.startswith("seller_order_count_") or c.startswith("seller_late_rate_")
    ]
    out = work.drop(columns=drop_cols)
    out = out.merge(hist, on="_row", how="left").drop(columns=["_row"])
    return out


def build_feature_table(
    tables: dict[str, pd.DataFrame],
    labeled_orders: pd.DataFrame,
) -> pd.DataFrame:
    """Build one-row-per-order feature table with label."""
    base = _order_level_basket(tables, labeled_orders)
    base = _add_time_parts(base)
    base = _seller_history_features(base)

    base["payment_type_primary"] = base["payment_type_primary"].fillna("unknown").astype(str)
    base["customer_state"] = base["customer_state"].fillna("unknown").astype(str)
    base["seller_state_primary"] = base["seller_state_primary"].fillna("unknown").astype(str)
    base["installment_count"] = base["installment_count"].fillna(1).astype(float)
    for col in [
        "item_count",
        "basket_value",
        "freight_value",
        "seller_count",
        "category_count",
        "estimated_delivery_horizon_days",
        "geo_distance_km",
    ]:
        base[col] = base[col].fillna(0).astype(float)

    required = FEATURE_COLUMNS + ["late_delivery", "order_id", "seller_id", "prediction_ts"]
    missing = [c for c in required if c not in base.columns]
    if missing:
        raise ValueError(f"Feature build missing columns: {missing}")

    logger.info("Feature table rows=%s cols=%s", f"{len(base):,}", len(FEATURE_COLUMNS))
    return base.reset_index(drop=True)
