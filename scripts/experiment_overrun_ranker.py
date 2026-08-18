#!/usr/bin/env python3
"""
Cheap experiment: duration regression vs promise-miss ranking.

Does NOT change the production classifier. Reuses existing PIT features + temporal split.

Scores compared on the *same* test window:
  - duration_minus_promise: pred(delivery_days) - promised_horizon
  - duration_minus_promise_no_h: same, but horizon excluded from X
  - days_late_regression: pred(delivered - estimated)
  - promise_miss_binary: P(delivered > estimated)
  - long_delivery_binary: P(delivery_days > 14) ranked against miss labels (cross-eval)

Write artifacts/overrun_experiment.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import OneHotEncoder

from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.splits import temporal_split
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.assembler import make_preprocessor, select_feature_frame
from olist_ml.features.build import build_feature_table
from olist_ml.features.contracts import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from olist_ml.training.train import train_model_bundle

REG_PARAMS = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "objective": "reg:squarederror",
    "n_jobs": 2,
    "verbosity": 0,
}

CLF_PARAMS = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
}


def _rank_report(y: np.ndarray, score: np.ndarray) -> dict[str, Any]:
    from sklearn.metrics import average_precision_score, roc_auc_score

    from olist_ml.training.evaluate import threshold_capacity_table

    if y.sum() < 1 or (1 - y).sum() < 1:
        return {
            "pr_auc": float("nan"),
            "roc_auc": float("nan"),
            "precision_at_10pct": None,
            "lift_at_10pct": None,
            "base_rate": float(y.mean()),
        }
    pr = float(average_precision_score(y, score))
    roc = float(roc_auc_score(y, score))
    cap = threshold_capacity_table(y, score)
    cap10 = next((r for r in cap.to_dict("records") if abs(r["capacity"] - 0.1) < 1e-9), None)
    base = float(y.mean())
    return {
        "pr_auc": pr,
        "roc_auc": roc,
        "precision_at_10pct": cap10["precision"] if cap10 else None,
        "lift_at_10pct": (cap10["precision"] / base) if cap10 and base > 0 else None,
        "base_rate": base,
    }

def _fit_regressor(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_valid: np.ndarray,
    y_valid: np.ndarray,
    seed: int = 42,
) -> xgb.XGBRegressor:
    model = xgb.XGBRegressor(**REG_PARAMS, random_state=seed, early_stopping_rounds=40)
    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)
    return model


def _pre_without_horizon() -> ColumnTransformer:
    nums = [c for c in NUMERIC_FEATURES if c != "estimated_delivery_horizon_days"]
    return ColumnTransformer(
        transformers=[
            ("num", "passthrough", nums),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )


def _select_no_horizon(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in NUMERIC_FEATURES if c != "estimated_delivery_horizon_days"] + list(
        CATEGORICAL_FEATURES
    )
    return df[cols].copy()


def main() -> None:
    tables = load_olist_tables(Path("data/raw"))
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled)
    features["promised_horizon"] = features["estimated_delivery_horizon_days"].astype(float)
    features["days_late"] = features["delivery_days"].astype(float) - features["promised_horizon"]

    splits = temporal_split(features)
    train, valid, test = splits.train, splits.validation, splits.test

    Xtr = select_feature_frame(train)
    Xva = select_feature_frame(valid)
    Xte = select_feature_frame(test)
    pre = make_preprocessor()
    Xtr_m = pre.fit_transform(Xtr)
    Xva_m = pre.transform(Xva)
    Xte_m = pre.transform(Xte)

    pre_nh = _pre_without_horizon()
    Xtr_nh = pre_nh.fit_transform(_select_no_horizon(train))
    Xva_nh = pre_nh.transform(_select_no_horizon(valid))
    Xte_nh = pre_nh.transform(_select_no_horizon(test))

    y_days_tr = train["delivery_days"].to_numpy()
    y_days_va = valid["delivery_days"].to_numpy()
    y_days_te = test["delivery_days"].to_numpy()
    y_late_tr = train["days_late"].to_numpy()
    y_late_va = valid["days_late"].to_numpy()
    h_te = test["promised_horizon"].to_numpy()

    dur = _fit_regressor(Xtr_m, y_days_tr, Xva_m, y_days_va)
    pred_days = dur.predict(Xte_m)
    overrun = pred_days - h_te

    dur_nh = _fit_regressor(Xtr_nh, y_days_tr, Xva_nh, y_days_va)
    pred_days_nh = dur_nh.predict(Xte_nh)
    overrun_nh = pred_days_nh - h_te

    late_reg = _fit_regressor(Xtr_m, y_late_tr, Xva_m, y_late_va)
    pred_days_late = late_reg.predict(Xte_m)

    miss_clf = train_model_bundle(
        Xtr,
        train["promise_miss"].to_numpy(),
        best_params=CLF_PARAMS,
        seed=42,
        X_df_valid=Xva,
        y_valid=valid["promise_miss"].to_numpy(),
    )
    miss_proba = miss_clf.predict_proba(Xte)[:, 1]

    long_clf = train_model_bundle(
        Xtr,
        train["long_delivery"].to_numpy(),
        best_params=CLF_PARAMS,
        seed=42,
        X_df_valid=Xva,
        y_valid=valid["long_delivery"].to_numpy(),
    )
    long_proba = long_clf.predict_proba(Xte)[:, 1]

    y_miss = test["promise_miss"].to_numpy().astype(int)
    y_late3 = (test["days_late"].to_numpy() > 3).astype(int)
    y_late7 = (test["days_late"].to_numpy() > 7).astype(int)
    y_long = test["long_delivery"].to_numpy().astype(int)

    scores = {
        "duration_minus_promise": overrun,
        "duration_minus_promise_no_horizon_in_X": overrun_nh,
        "days_late_regression": pred_days_late,
        "promise_miss_binary": miss_proba,
        "long_delivery_binary": long_proba,
    }
    labels = {
        "promise_miss": y_miss,
        "days_late_gt_3": y_late3,
        "days_late_gt_7": y_late7,
        "long_delivery_gt_14": y_long,
    }

    ranking: dict[str, Any] = {}
    for sname, score in scores.items():
        ranking[sname] = {lab: _rank_report(y, score) for lab, y in labels.items()}

    report = {
        "n_train": int(len(train)),
        "n_valid": int(len(valid)),
        "n_test": int(len(test)),
        "test_promise_miss_rate": float(y_miss.mean()),
        "test_long_delivery_rate": float(y_long.mean()),
        "test_days_late_mean": float(test["days_late"].mean()),
        "test_days_late_median": float(test["days_late"].median()),
        "duration_mae": float(mean_absolute_error(y_days_te, pred_days)),
        "duration_r2": float(r2_score(y_days_te, pred_days)),
        "duration_no_h_mae": float(mean_absolute_error(y_days_te, pred_days_nh)),
        "duration_no_h_r2": float(r2_score(y_days_te, pred_days_nh)),
        "days_late_mae": float(mean_absolute_error(test["days_late"].to_numpy(), pred_days_late)),
        "days_late_r2": float(r2_score(test["days_late"].to_numpy(), pred_days_late)),
        "mean_pred_days": float(np.mean(pred_days)),
        "mean_promised_horizon": float(np.mean(h_te)),
        "mean_overrun": float(np.mean(overrun)),
        "corr_pred_days_vs_horizon": float(np.corrcoef(pred_days, h_te)[0, 1]),
        "ranking": ranking,
        "note": (
            "Higher PR-AUC on promise_miss is the salvage metric. "
            "duration_minus_promise is pred(delivery_days)-promised_horizon."
        ),
    }
    out = Path("artifacts/overrun_experiment.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
