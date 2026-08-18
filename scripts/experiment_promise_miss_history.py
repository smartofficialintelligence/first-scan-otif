#!/usr/bin/env python3
"""
Screen: can promise-miss get to a usable ranker if we (a) redefine PIT
history on miss instead of >14d duration, (b) add route combo rates,
(c) add shipping_limit tightness + seller dispatch-miss history?

Does NOT change the production classifier or feature contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.splits import temporal_split
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.build import _pit_window_stats, build_feature_table
from olist_ml.features.contracts import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from olist_ml.training.evaluate import threshold_capacity_table

CLF_PARAMS = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "objective": "binary:logistic",
    "eval_metric": "aucpr",
    "n_jobs": 2,
    "verbosity": 0,
    "early_stopping_rounds": 40,
}

DURATION_RATE_COLS = [
    "seller_late_rate_7d",
    "seller_late_rate_30d",
    "seller_late_rate_90d",
    "customer_late_rate_90d",
    "category_late_rate_30d",
    "category_late_rate_90d",
]


def _rank_report(y: np.ndarray, score: np.ndarray) -> dict[str, Any]:
    if y.sum() < 1 or (1 - y).sum() < 1:
        return {"pr_auc": float("nan"), "roc_auc": float("nan"), "base_rate": float(y.mean())}
    pr = float(average_precision_score(y, score))
    roc = float(roc_auc_score(y, score))
    cap = threshold_capacity_table(y, score)
    recs = {r["capacity"]: r for r in cap.to_dict("records")}

    def _at(c: float) -> dict[str, float | None]:
        row = recs.get(c)
        base = float(y.mean())
        if not row:
            return {"precision": None, "recall": None, "lift": None}
        return {
            "precision": float(row["precision"]),
            "recall": float(row["recall"]),
            "lift": (float(row["precision"]) / base) if base > 0 else None,
        }

    return {
        "pr_auc": pr,
        "roc_auc": roc,
        "base_rate": float(y.mean()),
        "at_5pct": _at(0.05),
        "at_10pct": _at(0.10),
        "at_20pct": _at(0.20),
    }


def _attach_rates(
    df: pd.DataFrame,
    *,
    entity_col: str,
    rate_source: str,
    count_prefix: str,
    rate_prefix: str,
    windows: dict[str, int],
) -> pd.DataFrame:
    stats = _pit_window_stats(
        df,
        entity_col=entity_col,
        windows_days=windows,
        count_prefix=count_prefix,
        rate_prefix=rate_prefix,
        rate_source=rate_source,
    )
    out = df.copy()
    out["_row"] = np.arange(len(out))
    out = out.merge(stats, on="_row", how="left")
    return out.drop(columns=["_row"])


def _attach_outcome_available_rates(
    df: pd.DataFrame,
    *,
    entity_col: str,
    rate_source: str,
    outcome_col: str,
    count_prefix: str,
    rate_prefix: str,
    windows: dict[str, int],
) -> pd.DataFrame:
    """Prior orders of the entity whose *outcome* was already known (delivered < now)."""
    work = df[[entity_col, "prediction_ts", rate_source, outcome_col]].copy()
    work["_row"] = np.arange(len(work))
    work["prediction_ts"] = pd.to_datetime(work["prediction_ts"], utc=True)
    work[outcome_col] = pd.to_datetime(work[outcome_col], utc=True, errors="coerce")
    work = work.sort_values([entity_col, "prediction_ts", "_row"])

    out_rows: list[dict[str, float | int]] = []
    ns_day = 24 * 3600 * 1_000_000_000
    for _, g in work.groupby(entity_col, sort=False):
        t_ns = g["prediction_ts"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        o_ns = g[outcome_col].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        y = g[rate_source].to_numpy(dtype=float)
        rows = g["_row"].to_numpy()
        for i in range(len(g)):
            rec: dict[str, float | int] = {"_row": int(rows[i])}
            t_i = t_ns[i]
            known = (t_ns < t_i) & (o_ns < t_i)
            for suffix, days in windows.items():
                start_ns = t_i - int(days) * ns_day
                in_win = known & (t_ns >= start_ns)
                count = int(in_win.sum())
                rec[f"{count_prefix}_{suffix}"] = float(count)
                rec[f"{rate_prefix}_{suffix}"] = float(y[in_win].mean()) if count else 0.0
            out_rows.append(rec)
    stats = pd.DataFrame.from_records(out_rows)
    out = df.copy()
    out["_row"] = np.arange(len(out))
    out = out.merge(stats, on="_row", how="left")
    return out.drop(columns=["_row"])


def _preprocessor(num_cols: list[str], cat_cols: list[str]) -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", "passthrough", num_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
        ],
        remainder="drop",
    )


def _fit_clf(
    train: pd.DataFrame,
    valid: pd.DataFrame,
    test: pd.DataFrame,
    *,
    y_col: str,
    num_cols: list[str],
    cat_cols: list[str],
) -> tuple[np.ndarray, dict[str, float]]:
    pre = _preprocessor(num_cols, cat_cols)
    cols = num_cols + cat_cols
    Xtr = pre.fit_transform(train[cols])
    Xva = pre.transform(valid[cols])
    Xte = pre.transform(test[cols])
    ytr = train[y_col].to_numpy().astype(int)
    yva = valid[y_col].to_numpy().astype(int)
    pos = max(int(ytr.sum()), 1)
    neg = max(int((1 - ytr).sum()), 1)
    model = XGBClassifier(**CLF_PARAMS, random_state=42, scale_pos_weight=neg / pos)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    proba = model.predict_proba(Xte)[:, 1]
    names = list(pre.get_feature_names_out())
    gain = model.feature_importances_
    top = sorted(zip(names, gain, strict=True), key=lambda x: -x[1])[:12]
    return proba, {n: float(g) for n, g in top}


def _univariate_pr(test: pd.DataFrame, y: np.ndarray, cols: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in cols:
        if c not in test.columns:
            continue
        s = test[c].to_numpy(dtype=float)
        if np.nanstd(s) == 0:
            continue
        out[c] = float(average_precision_score(y, np.nan_to_num(s, nan=0.0)))
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:20])


def main() -> None:
    tables = load_olist_tables(Path("data/raw"))
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled)

    items = tables["order_items"].copy()
    items["shipping_limit_date"] = pd.to_datetime(items["shipping_limit_date"], utc=True, errors="coerce")
    lim = items.groupby("order_id", as_index=False).agg(
        shipping_limit_date=("shipping_limit_date", "min"),
    )
    features = features.merge(lim, on="order_id", how="left")
    pred = pd.to_datetime(features["prediction_ts"], utc=True)
    features["shipping_limit_horizon_days"] = (
        features["shipping_limit_date"] - pred
    ).dt.total_seconds() / 86400.0
    features["shipping_limit_horizon_days"] = (
        features["shipping_limit_horizon_days"].fillna(features["shipping_limit_horizon_days"].median()).clip(-5, 60)
    )

    carrier = pd.to_datetime(features["order_delivered_carrier_date"], utc=True, errors="coerce")
    features["limit_miss"] = (
        carrier.notna() & features["shipping_limit_date"].notna() & (carrier > features["shipping_limit_date"])
    ).astype(int)
    features["promise_miss"] = features["promise_miss"].astype(int)
    features["route_key"] = (
        features["seller_state_primary"].fillna("unknown").astype(str)
        + "|"
        + features["customer_state"].fillna("unknown").astype(str)
    )
    features["seller_dest_key"] = (
        features["seller_id"].astype(str)
        + "|"
        + features["customer_state"].fillna("unknown").astype(str)
    )

    # Place-time PIT (prior order placed before now) — matches production machinery.
    features = _attach_rates(
        features,
        entity_col="seller_id",
        rate_source="promise_miss",
        count_prefix="seller_miss_count",
        rate_prefix="seller_miss_rate",
        windows={"7d": 7, "30d": 30, "90d": 90},
    )
    features = _attach_rates(
        features,
        entity_col="customer_id",
        rate_source="promise_miss",
        count_prefix="customer_miss_count",
        rate_prefix="customer_miss_rate",
        windows={"90d": 90},
    )
    features = _attach_rates(
        features,
        entity_col="primary_category",
        rate_source="promise_miss",
        count_prefix="category_miss_count",
        rate_prefix="category_miss_rate",
        windows={"30d": 30, "90d": 90},
    )
    features = _attach_rates(
        features,
        entity_col="route_key",
        rate_source="promise_miss",
        count_prefix="route_miss_count",
        rate_prefix="route_miss_rate",
        windows={"30d": 30, "90d": 90},
    )
    features = _attach_rates(
        features,
        entity_col="seller_dest_key",
        rate_source="promise_miss",
        count_prefix="seller_dest_miss_count",
        rate_prefix="seller_dest_miss_rate",
        windows={"30d": 30, "90d": 90},
    )
    features = _attach_rates(
        features,
        entity_col="seller_id",
        rate_source="limit_miss",
        count_prefix="seller_limit_miss_count",
        rate_prefix="seller_limit_miss_rate",
        windows={"30d": 30, "90d": 90},
    )

    # Stricter seller miss history: outcome already observed.
    features = _attach_outcome_available_rates(
        features,
        entity_col="seller_id",
        rate_source="promise_miss",
        outcome_col="order_delivered_customer_date",
        count_prefix="seller_miss_obs_count",
        rate_prefix="seller_miss_obs_rate",
        windows={"30d": 30, "90d": 90},
    )

    miss_rate_cols = [
        "seller_miss_rate_7d",
        "seller_miss_rate_30d",
        "seller_miss_rate_90d",
        "customer_miss_rate_90d",
        "category_miss_rate_30d",
        "category_miss_rate_90d",
    ]
    combo_cols = [
        "route_miss_rate_30d",
        "route_miss_rate_90d",
        "route_miss_count_90d",
        "seller_dest_miss_rate_30d",
        "seller_dest_miss_rate_90d",
        "seller_dest_miss_count_90d",
    ]
    dispatch_cols = [
        "seller_limit_miss_rate_30d",
        "seller_limit_miss_rate_90d",
        "shipping_limit_horizon_days",
    ]
    obs_cols = ["seller_miss_obs_rate_30d", "seller_miss_obs_rate_90d"]

    splits = temporal_split(features)
    train, valid, test = splits.train, splits.validation, splits.test
    y_te = test["promise_miss"].to_numpy().astype(int)

    prod_num = list(NUMERIC_FEATURES)
    prod_cat = list(CATEGORICAL_FEATURES)
    miss_num = [c for c in prod_num if c not in DURATION_RATE_COLS] + miss_rate_cols
    combo_num = miss_num + combo_cols
    full_num = combo_num + dispatch_cols + obs_cols
    no_horizon_num = [c for c in full_num if c != "estimated_delivery_horizon_days"]

    variants: dict[str, tuple[list[str], list[str]]] = {
        "A_production_duration_rates": (prod_num, prod_cat),
        "B_relabel_history_to_promise_miss": (miss_num, prod_cat),
        "C_plus_route_combos": (combo_num, prod_cat),
        "D_plus_limit_and_dispatch_hist": (full_num, prod_cat),
        "E_D_without_customer_horizon": (no_horizon_num, prod_cat),
    }

    ranking: dict[str, Any] = {}
    importances: dict[str, dict[str, float]] = {}
    for name, (nums, cats) in variants.items():
        proba, top = _fit_clf(train, valid, test, y_col="promise_miss", num_cols=nums, cat_cols=cats)
        ranking[name] = _rank_report(y_te, proba)
        importances[name] = top
        print(name, json.dumps(ranking[name], indent=None))

    # Same full feature set, but target = shipping_limit miss (seller SLA).
    lim_proba, lim_top = _fit_clf(
        train, valid, test, y_col="limit_miss", num_cols=full_num, cat_cols=prod_cat
    )
    y_lim = test["limit_miss"].to_numpy().astype(int)
    ranking["F_same_X_target_limit_miss"] = _rank_report(y_lim, lim_proba)
    importances["F_same_X_target_limit_miss"] = lim_top

    uni_cols = DURATION_RATE_COLS + miss_rate_cols + combo_cols + dispatch_cols + obs_cols
    uni_cols += ["estimated_delivery_horizon_days", "geo_distance_km", "freight_to_basket_ratio"]

    report = {
        "n_train": int(len(train)),
        "n_valid": int(len(valid)),
        "n_test": int(len(test)),
        "test_promise_miss_rate": float(y_te.mean()),
        "test_limit_miss_rate": float(y_lim.mean()),
        "train_promise_miss_rate": float(train["promise_miss"].mean()),
        "note": (
            "A uses production late rates (defined on >14d). "
            "B–E retarget those rates to promise_miss and add combos. "
            "History is PIT (prior prediction_ts); obs_* also requires prior delivery < now."
        ),
        "public_honest_bar_pr_auc": 0.335,
        "ranking": ranking,
        "top_importances": importances,
        "univariate_pr_auc_on_test_promise_miss": _univariate_pr(test, y_te, uni_cols),
        "univariate_pr_auc_on_test_limit_miss": _univariate_pr(test, y_lim, uni_cols),
    }
    out = Path("artifacts/promise_miss_history_experiment.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
