"""Offline feature builder (PIT-safe) for training and local assembly."""

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
    products = tables["products"].copy()
    prod_cols = ["product_id", "product_category_name"]
    if "product_weight_g" in products.columns:
        prod_cols.append("product_weight_g")
    products = products[prod_cols]
    items = items.merge(products, on="product_id", how="left")

    agg: dict[str, tuple[str, str]] = {
        "item_count": ("order_item_id", "count"),
        "basket_value": ("price", "sum"),
        "freight_value": ("freight_value", "sum"),
        "seller_count": ("seller_id", "nunique"),
        "category_count": ("product_category_name", "nunique"),
        "primary_seller_id": ("seller_id", "first"),
        "primary_category": ("product_category_name", "first"),
    }
    if "product_weight_g" in items.columns:
        agg["avg_product_weight_g"] = ("product_weight_g", "mean")

    basket = items.groupby("order_id", as_index=False).agg(**agg)

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
    sellers = (
        tables["sellers"][["seller_id", "seller_state", "seller_zip_code_prefix"]]
        .rename(columns={"seller_id": "primary_seller_id", "seller_state": "seller_state_primary"})
        .copy()
    )
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
    if "avg_product_weight_g" not in base.columns:
        base["avg_product_weight_g"] = 0.0
    return base


def _add_time_parts(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = pd.to_datetime(out["prediction_ts"], utc=True)
    out["purchase_hour"] = ts.dt.hour.astype(float)
    out["purchase_dow"] = ts.dt.dayofweek.astype(float)
    out["purchase_month"] = ts.dt.month.astype(float)
    out["is_weekend"] = (ts.dt.dayofweek >= 5).astype(float)
    # Known at prediction time (approval lag).
    if "order_purchase_timestamp" in out.columns:
        purchase = pd.to_datetime(out["order_purchase_timestamp"], utc=True, errors="coerce")
        out["approval_lag_hours"] = ((ts - purchase).dt.total_seconds() / 3600.0).clip(lower=0).fillna(0.0)
    else:
        out["approval_lag_hours"] = 0.0
    return out


def _pit_window_stats(
    df: pd.DataFrame,
    *,
    entity_col: str,
    time_col: str = "prediction_ts",
    windows_days: dict[str, int],
    count_prefix: str,
    rate_prefix: str | None = None,
    rate_source: str = "long_delivery",
    mean_specs: list[tuple[str, str]] | None = None,
) -> pd.DataFrame:
    """
    Point-in-time rolling stats per entity (strictly before current row).

    mean_specs: list of (output_col_prefix, source_col) producing `{prefix}_{window}`.
    """
    mean_specs = mean_specs or []
    work = df[[entity_col, time_col, rate_source, *{src for _, src in mean_specs}]].copy()
    work["_row"] = np.arange(len(work))
    work[time_col] = pd.to_datetime(work[time_col], utc=True)
    work = work.sort_values([entity_col, time_col, "_row"])

    out_rows: list[dict[str, float | int]] = []
    for _, g in work.groupby(entity_col, sort=False):
        times = g[time_col].to_numpy(dtype="datetime64[ns]")
        # ns integers for searchsorted
        t_ns = times.astype("datetime64[ns]").astype(np.int64)
        late = g[rate_source].to_numpy(dtype=float)
        means_src = {src: g[src].to_numpy(dtype=float) for _, src in mean_specs}
        rows = g["_row"].to_numpy()
        csum_late = np.concatenate([[0.0], np.cumsum(late)])
        csum_means = {
            src: np.concatenate([[0.0], np.cumsum(np.nan_to_num(arr, nan=0.0))])
            for src, arr in means_src.items()
        }
        for i in range(len(g)):
            rec: dict[str, float | int] = {"_row": int(rows[i])}
            t_i = t_ns[i]
            for suffix, days in windows_days.items():
                start_ns = t_i - int(days) * 24 * 3600 * 1_000_000_000
                # priors: times < t_i and times >= start
                left = int(np.searchsorted(t_ns, start_ns, side="left"))
                right = i  # exclusive — excludes current
                count = max(0, right - left)
                rec[f"{count_prefix}_{suffix}"] = float(count)
                if rate_prefix is not None:
                    if count:
                        rate = float((csum_late[right] - csum_late[left]) / count)
                    else:
                        rate = 0.0
                    rec[f"{rate_prefix}_{suffix}"] = rate
                for prefix, src in mean_specs:
                    if count:
                        avg = float((csum_means[src][right] - csum_means[src][left]) / count)
                    else:
                        avg = 0.0
                    rec[f"{prefix}_{suffix}"] = avg
            out_rows.append(rec)

    return pd.DataFrame.from_records(out_rows)


def _attach_history(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["prediction_ts"] = pd.to_datetime(out["prediction_ts"], utc=True)

    seller = _pit_window_stats(
        out,
        entity_col="seller_id",
        windows_days={"7d": 7, "30d": 30, "90d": 90},
        count_prefix="seller_order_count",
        rate_prefix="seller_late_rate",
        mean_specs=[
            ("seller_avg_freight", "freight_value"),
            ("seller_avg_basket", "basket_value"),
        ],
    )
    # Keep only 30/90 for freight/basket averages (drop unused 7d columns).
    drop_avg_7d = [c for c in seller.columns if c.endswith("_7d") and c.startswith("seller_avg_")]
    seller = seller.drop(columns=drop_avg_7d)

    customer = _pit_window_stats(
        out,
        entity_col="customer_id",
        windows_days={"30d": 30, "90d": 90},
        count_prefix="customer_order_count",
        rate_prefix="customer_late_rate",
    )
    # Only keep customer_late_rate_90d per contract (drop 30d rate if present).
    if "customer_late_rate_30d" in customer.columns:
        customer = customer.drop(columns=["customer_late_rate_30d"])

    # Category history uses primary_category; unknown buckets share history.
    cat_src = out.copy()
    cat_src["primary_category"] = cat_src["primary_category"].fillna("unknown").astype(str)
    category = _pit_window_stats(
        cat_src,
        entity_col="primary_category",
        windows_days={"30d": 30, "90d": 90},
        count_prefix="category_order_count",
        rate_prefix="category_late_rate",
    )
    if "category_order_count_30d" in category.columns:
        category = category.drop(columns=["category_order_count_30d"])

    out["_row"] = np.arange(len(out))
    out = out.merge(seller, on="_row", how="left")
    out = out.merge(customer, on="_row", how="left")
    out = out.merge(category, on="_row", how="left")
    return out.drop(columns=["_row"])


def build_feature_table(
    tables: dict[str, pd.DataFrame],
    labeled_orders: pd.DataFrame,
) -> pd.DataFrame:
    """Build one-row-per-order feature table with label."""
    base = _order_level_basket(tables, labeled_orders)
    base = _add_time_parts(base)
    base = _attach_history(base)

    base["payment_type_primary"] = base["payment_type_primary"].fillna("unknown").astype(str).str.lower()
    base["customer_state"] = base["customer_state"].fillna("unknown").astype(str).str.lower()
    base["seller_state_primary"] = base["seller_state_primary"].fillna("unknown").astype(str).str.lower()
    base["primary_category"] = base["primary_category"].fillna("unknown").astype(str).str.lower()
    base["installment_count"] = base["installment_count"].fillna(1).astype(float)
    base["same_state"] = (
        (base["customer_state"] == base["seller_state_primary"])
        & (base["customer_state"] != "unknown")
    ).astype(float)
    base["freight_to_basket_ratio"] = np.where(
        base["basket_value"].astype(float) > 0,
        base["freight_value"].astype(float) / base["basket_value"].astype(float),
        0.0,
    )

    fill0 = [
        "item_count",
        "basket_value",
        "freight_value",
        "freight_to_basket_ratio",
        "seller_count",
        "category_count",
        "estimated_delivery_horizon_days",
        "approval_lag_hours",
        "geo_distance_km",
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
    ]
    for col in fill0:
        base[col] = base[col].fillna(0).astype(float)

    required = FEATURE_COLUMNS + ["long_delivery", "order_id", "seller_id", "prediction_ts"]
    missing = [c for c in required if c not in base.columns]
    if missing:
        raise ValueError(f"Feature build missing columns: {missing}")

    logger.info("Feature table rows=%s cols=%s", f"{len(base):,}", len(FEATURE_COLUMNS))
    return base.reset_index(drop=True)
