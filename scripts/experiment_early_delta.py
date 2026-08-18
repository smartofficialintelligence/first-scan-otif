#!/usr/bin/env python3
"""
Can we predict beating the promise (early arrival), or the day delta
(promise vs actual)? Production features, temporal split. No champion change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    mean_absolute_error,
    r2_score,
    roc_auc_score,
    root_mean_squared_error,
)
from xgboost import XGBClassifier, XGBRegressor

from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.splits import temporal_split
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.assembler import make_preprocessor, select_feature_frame
from olist_ml.features.build import build_feature_table
from olist_ml.training.evaluate import threshold_capacity_table

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
    "early_stopping_rounds": 40,
}

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


def _clf_report(y: np.ndarray, score: np.ndarray) -> dict[str, Any]:
    base = float(y.mean())
    if y.sum() < 5 or (1 - y).sum() < 5:
        return {"n": int(len(y)), "base_rate": base, "skipped": True}
    cap = {r["capacity"]: r for r in threshold_capacity_table(y, score).to_dict("records")}
    at10 = cap.get(0.10, {})
    prec = float(at10.get("precision", float("nan")))
    return {
        "n": int(len(y)),
        "n_pos": int(y.sum()),
        "base_rate": base,
        "pr_auc": float(average_precision_score(y, score)),
        "roc_auc": float(roc_auc_score(y, score)),
        "precision_at_10pct": prec,
        "lift_at_10pct": (prec / base) if base > 0 else None,
        "dummy_pr_auc": base,
    }


def _reg_report(y: np.ndarray, pred: np.ndarray, *, naive: np.ndarray) -> dict[str, Any]:
    return {
        "n": int(len(y)),
        "y_mean": float(np.mean(y)),
        "y_median": float(np.median(y)),
        "y_std": float(np.std(y)),
        "pred_mean": float(np.mean(pred)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(root_mean_squared_error(y, pred)),
        "r2": float(r2_score(y, pred)),
        "naive_mae": float(mean_absolute_error(y, naive)),
        "naive_rmse": float(root_mean_squared_error(y, naive)),
        "naive_r2": float(r2_score(y, naive)),
        "mae_vs_naive": float(mean_absolute_error(y, naive) - mean_absolute_error(y, pred)),
        "corr": float(np.corrcoef(y, pred)[0, 1]) if np.std(pred) > 0 else float("nan"),
    }


def _fit_reg(Xtr, ytr, Xva, yva) -> XGBRegressor:
    m = XGBRegressor(**REG_PARAMS, random_state=42)
    m.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    return m


def _fit_clf(Xtr, ytr, Xva, yva) -> XGBClassifier:
    pos = max(int(ytr.sum()), 1)
    neg = max(int((1 - ytr).sum()), 1)
    m = XGBClassifier(**CLF_PARAMS, random_state=42, scale_pos_weight=neg / pos)
    m.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    return m


def main() -> None:
    tables = load_olist_tables(Path("data/raw"))
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled)
    h = features["estimated_delivery_horizon_days"].astype(float)
    features["days_late"] = features["delivery_days"].astype(float) - h
    features["days_early"] = -features["days_late"]
    features["abs_delta"] = features["days_late"].abs()
    features["is_early"] = (features["days_late"] < 0).astype(int)
    features["is_ontime_day"] = (features["days_late"].round() == 0).astype(int)
    features["is_late"] = (features["days_late"] > 0).astype(int)
    features["early_ge_3"] = (features["days_early"] >= 3).astype(int)
    features["early_ge_7"] = (features["days_early"] >= 7).astype(int)
    features["early_ge_14"] = (features["days_early"] >= 14).astype(int)

    splits = temporal_split(features)
    train, valid, test = splits.train, splits.validation, splits.test

    pre = make_preprocessor()
    Xtr = pre.fit_transform(select_feature_frame(train))
    Xva = pre.transform(select_feature_frame(valid))
    Xte = pre.transform(select_feature_frame(test))

    y_early = {c: test[c].to_numpy().astype(int) for c in ["is_early", "early_ge_3", "early_ge_7", "early_ge_14", "is_late"]}
    dist = {
        "test_n": int(len(test)),
        "early_rate": float(test["is_early"].mean()),
        "same_calendar_day_rate": float(test["is_ontime_day"].mean()),
        "late_rate": float(test["is_late"].mean()),
        "early_ge_3": float(test["early_ge_3"].mean()),
        "early_ge_7": float(test["early_ge_7"].mean()),
        "early_ge_14": float(test["early_ge_14"].mean()),
        "days_early_mean": float(test["days_early"].mean()),
        "days_early_median": float(test["days_early"].median()),
        "days_early_p10": float(test["days_early"].quantile(0.10)),
        "days_early_p90": float(test["days_early"].quantile(0.90)),
        "abs_delta_mean": float(test["abs_delta"].mean()),
        "abs_delta_median": float(test["abs_delta"].median()),
    }
    print("distribution", json.dumps(dist, indent=2))

    naive_early = np.full(len(test), float(train["days_early"].mean()))
    naive_abs = np.full(len(test), float(train["abs_delta"].mean()))
    naive_dur = np.full(len(test), float(train["delivery_days"].mean()))

    dur = _fit_reg(Xtr, train["delivery_days"].to_numpy(), Xva, valid["delivery_days"].to_numpy())
    pred_days = dur.predict(Xte)
    h_te = test["estimated_delivery_horizon_days"].to_numpy(dtype=float)
    implied_early = h_te - pred_days  # predicted days before promise

    early_reg = _fit_reg(Xtr, train["days_early"].to_numpy(), Xva, valid["days_early"].to_numpy())
    pred_early = early_reg.predict(Xte)

    abs_reg = _fit_reg(Xtr, train["abs_delta"].to_numpy(), Xva, valid["abs_delta"].to_numpy())
    pred_abs = abs_reg.predict(Xte)

    ranking: dict[str, Any] = {}
    for name, ycol in [
        ("is_early", "is_early"),
        ("early_ge_3d", "early_ge_3"),
        ("early_ge_7d", "early_ge_7"),
        ("early_ge_14d", "early_ge_14"),
        ("is_late", "is_late"),
    ]:
        ytr, yva, yte = train[ycol].to_numpy().astype(int), valid[ycol].to_numpy().astype(int), y_early[ycol]
        clf = _fit_clf(Xtr, ytr, Xva, yva)
        proba = clf.predict_proba(Xte)[:, 1]
        ranking[f"binary_{name}"] = _clf_report(yte, proba)

    # Rank "will beat promise" using regression scores (higher = more early).
    ranking["reg_days_early_as_early_score"] = _clf_report(y_early["is_early"], pred_early)
    ranking["implied_horizon_minus_duration_as_early_score"] = _clf_report(y_early["is_early"], implied_early)
    ranking["reg_days_early_as_early7_score"] = _clf_report(y_early["early_ge_7"], pred_early)
    ranking["implied_as_early7_score"] = _clf_report(y_early["early_ge_7"], implied_early)
    ranking["neg_reg_early_as_late_score"] = _clf_report(y_early["is_late"], -pred_early)

    regression = {
        "delivery_days": _reg_report(
            test["delivery_days"].to_numpy(), pred_days, naive=naive_dur
        ),
        "days_early_signed": _reg_report(
            test["days_early"].to_numpy(), pred_early, naive=naive_early
        ),
        "days_early_implied_from_duration": _reg_report(
            test["days_early"].to_numpy(), implied_early, naive=naive_early
        ),
        "abs_delta": _reg_report(
            test["abs_delta"].to_numpy(), pred_abs, naive=naive_abs
        ),
        "abs_delta_from_signed_reg": _reg_report(
            test["abs_delta"].to_numpy(), np.abs(pred_early), naive=naive_abs
        ),
    }

    # How often signed residual is in the right direction vs "always early by train mean".
    true_early = test["days_early"].to_numpy()
    sign_ok = float(np.mean(np.sign(pred_early) == np.sign(true_early)))
    within_3 = float(np.mean(np.abs(pred_early - true_early) <= 3))
    within_7 = float(np.mean(np.abs(pred_early - true_early) <= 7))
    naive_within_3 = float(np.mean(np.abs(naive_early - true_early) <= 3))
    naive_within_7 = float(np.mean(np.abs(naive_early - true_early) <= 7))

    report = {
        "distribution": dist,
        "sign_match_rate": sign_ok,
        "signed_reg_within_3d": within_3,
        "signed_reg_within_7d": within_7,
        "naive_mean_within_3d": naive_within_3,
        "naive_mean_within_7d": naive_within_7,
        "regression": regression,
        "ranking": ranking,
        "note": (
            "is_early is ~1-is_late except same-day. High base-rate PR-AUC is not a win. "
            "early_ge_7d / signed days_early are the honest 'beat the padded ETA' questions."
        ),
    }
    out = Path("artifacts/early_delta_experiment.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"distribution": dist, "regression": regression, "ranking": ranking}, indent=2))


if __name__ == "__main__":
    main()
