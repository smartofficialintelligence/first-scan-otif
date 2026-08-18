#!/usr/bin/env python3
"""
Does training on long (padded) promises drown customer-miss signal?

Split in time first, then filter by promised horizon so the calendar
window stays the same. Production feature contract; y = promise_miss.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from xgboost import XGBClassifier

from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.splits import temporal_split
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.assembler import make_preprocessor, select_feature_frame
from olist_ml.features.build import build_feature_table
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

CUTS = (7, 10, 14, 18, 21, 30)


def _report(y: np.ndarray, score: np.ndarray) -> dict[str, Any]:
    n_pos = int(y.sum())
    if n_pos < 5 or int((1 - y).sum()) < 5:
        return {
            "n": int(len(y)),
            "n_pos": n_pos,
            "base_rate": float(y.mean()) if len(y) else float("nan"),
            "pr_auc": float("nan"),
            "roc_auc": float("nan"),
            "skipped": True,
        }
    pr = float(average_precision_score(y, score))
    roc = float(roc_auc_score(y, score))
    cap = {r["capacity"]: r for r in threshold_capacity_table(y, score).to_dict("records")}
    base = float(y.mean())
    at10 = cap.get(0.10, {})
    prec10 = float(at10.get("precision", float("nan")))
    return {
        "n": int(len(y)),
        "n_pos": n_pos,
        "base_rate": base,
        "pr_auc": pr,
        "pr_auc_minus_base": pr - base,
        "roc_auc": roc,
        "precision_at_10pct": prec10,
        "lift_at_10pct": (prec10 / base) if base > 0 else None,
        "recall_at_10pct": float(at10.get("recall", float("nan"))),
    }


def _fit(
    train: pd.DataFrame,
    valid: pd.DataFrame,
    *,
    y_col: str = "promise_miss",
) -> XGBClassifier:
    pre = make_preprocessor()
    Xtr = pre.fit_transform(select_feature_frame(train))
    Xva = pre.transform(select_feature_frame(valid))
    ytr = train[y_col].to_numpy().astype(int)
    yva = valid[y_col].to_numpy().astype(int)
    pos = max(int(ytr.sum()), 1)
    neg = max(int((1 - ytr).sum()), 1)
    model = XGBClassifier(**CLF_PARAMS, random_state=42, scale_pos_weight=neg / pos)
    model.fit(Xtr, ytr, eval_set=[(Xva, yva)], verbose=False)
    model._pre = pre  # type: ignore[attr-defined]
    return model


def _score(model: XGBClassifier, df: pd.DataFrame) -> np.ndarray:
    Xt = model._pre.transform(select_feature_frame(df))  # type: ignore[attr-defined]
    return model.predict_proba(Xt)[:, 1]


def _mask(df: pd.DataFrame, op: str, cut: float) -> pd.Series:
    h = df["estimated_delivery_horizon_days"].astype(float)
    if op == "le":
        return h <= cut
    if op == "gt":
        return h > cut
    raise ValueError(op)


def main() -> None:
    tables = load_olist_tables(Path("data/raw"))
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled)
    features["promise_miss"] = features["promise_miss"].astype(int)
    splits = temporal_split(features)
    train, valid, test = splits.train, splits.validation, splits.test
    h_te = test["estimated_delivery_horizon_days"].astype(float)

    buckets = pd.cut(
        h_te,
        bins=[-np.inf, 7, 10, 14, 18, 21, 30, 45, np.inf],
        labels=["<=7", "7-10", "10-14", "14-18", "18-21", "21-30", "30-45", ">45"],
    )
    bucket_tbl = (
        test.assign(_b=buckets)
        .groupby("_b", observed=True)
        .agg(n=("promise_miss", "size"), miss_rate=("promise_miss", "mean"), med_h=("estimated_delivery_horizon_days", "median"))
        .reset_index()
        .rename(columns={"_b": "horizon_bucket"})
    )

    print("=== test miss rate by promised horizon ===")
    print(bucket_tbl.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    # Fit once on all training rows (the current setup).
    model_all = _fit(train, valid)
    p_all_test = _score(model_all, test)
    y_all = test["promise_miss"].to_numpy().astype(int)

    results: dict[str, Any] = {
        "n_train": int(len(train)),
        "n_valid": int(len(valid)),
        "n_test": int(len(test)),
        "test_overall": _report(y_all, p_all_test),
        "test_miss_by_horizon_bucket": bucket_tbl.to_dict(orient="records"),
        "cuts": {},
    }

    for cut in CUTS:
        tr_s, va_s = train.loc[_mask(train, "le", cut)], valid.loc[_mask(valid, "le", cut)]
        te_s, te_l = test.loc[_mask(test, "le", cut)], test.loc[_mask(test, "gt", cut)]
        if len(tr_s) < 200 or int(tr_s["promise_miss"].sum()) < 20:
            results["cuts"][str(cut)] = {"skipped": True, "n_train_short": int(len(tr_s))}
            continue

        model_short = _fit(tr_s, va_s if len(va_s) >= 50 and va_s["promise_miss"].nunique() == 2 else tr_s)
        p_short_on_short = _score(model_short, te_s)
        p_all_on_short = _score(model_all, te_s)
        y_s = te_s["promise_miss"].to_numpy().astype(int)

        row: dict[str, Any] = {
            "n_train_short": int(len(tr_s)),
            "train_short_miss_rate": float(tr_s["promise_miss"].mean()),
            "n_test_short": int(len(te_s)),
            "n_test_long": int(len(te_l)),
            "eval_short_train_short": _report(y_s, p_short_on_short),
            "eval_short_train_all": _report(y_s, p_all_on_short),
        }
        if len(te_l) >= 50 and te_l["promise_miss"].nunique() == 2:
            row["eval_long_train_all"] = _report(
                te_l["promise_miss"].to_numpy().astype(int),
                _score(model_all, te_l),
            )
            row["eval_long_train_short"] = _report(
                te_l["promise_miss"].to_numpy().astype(int),
                _score(model_short, te_l),
            )
        results["cuts"][str(cut)] = row
        ss = row["eval_short_train_short"]
        sa = row["eval_short_train_all"]
        print(
            f"cut<={cut:2d}d  n_tr={len(tr_s):5d} n_te={len(te_s):5d}  "
            f"base={ss['base_rate']:.3f}  "
            f"train_short PR-AUC={ss['pr_auc']:.3f} ROC={ss['roc_auc']:.3f} p@10={ss['precision_at_10pct']:.3f}  "
            f"train_all   PR-AUC={sa['pr_auc']:.3f} ROC={sa['roc_auc']:.3f} p@10={sa['precision_at_10pct']:.3f}"
        )

    out = Path("artifacts/short_promise_miss_experiment.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"test_overall": results["test_overall"]}, indent=2))


if __name__ == "__main__":
    main()
