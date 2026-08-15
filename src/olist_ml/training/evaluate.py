"""Evaluation metrics, bootstrap CIs, threshold tables."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
)

from olist_ml.logging import get_logger

logger = get_logger(__name__)


def expected_calibration_error(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        upper = bins[i + 1]
        if i < n_bins - 1:
            mask = (proba >= bins[i]) & (proba < upper)
        else:
            mask = (proba >= bins[i]) & (proba <= upper)
        if not np.any(mask):
            continue
        ece += mask.mean() * abs(y_true[mask].mean() - proba[mask].mean())
    return float(ece)


def classification_metrics(y_true: np.ndarray, proba: np.ndarray) -> dict[str, float]:
    out: dict[str, float] = {
        "pr_auc": float(average_precision_score(y_true, proba)),
        "brier": float(brier_score_loss(y_true, proba)),
        "ece": expected_calibration_error(y_true, proba),
    }
    if len(np.unique(y_true)) > 1:
        out["roc_auc"] = float(roc_auc_score(y_true, proba))
    else:
        out["roc_auc"] = float("nan")
    return out


def bootstrap_metrics(
    y_true: np.ndarray,
    proba: np.ndarray,
    *,
    n_bootstrap: int = 200,
    seed: int = 42,
) -> dict[str, dict[str, float]]:
    rng = np.random.default_rng(seed)
    n = len(y_true)
    bucket: dict[str, list[float]] = {"pr_auc": [], "roc_auc": [], "brier": []}
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        if len(np.unique(y_true[idx])) < 2:
            continue
        m = classification_metrics(y_true[idx], proba[idx])
        for k in bucket:
            bucket[k].append(m[k])
    summary: dict[str, dict[str, float]] = {}
    for k, vals in bucket.items():
        arr = np.asarray(vals, dtype=float)
        if len(arr) == 0:
            summary[k] = {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}
        else:
            summary[k] = {
                "mean": float(arr.mean()),
                "ci_low": float(np.percentile(arr, 2.5)),
                "ci_high": float(np.percentile(arr, 97.5)),
            }
    return summary


def threshold_capacity_table(
    y_true: np.ndarray,
    proba: np.ndarray,
    capacities: tuple[float, ...] = (0.05, 0.10, 0.20),
) -> pd.DataFrame:
    """Precision/recall when flagging top capacity fraction by risk."""
    n = len(proba)
    order = np.argsort(-proba)
    rows = []
    for cap in capacities:
        k = max(1, int(n * cap))
        flagged = order[:k]
        y_hat = np.zeros(n, dtype=int)
        y_hat[flagged] = 1
        tp = int(((y_hat == 1) & (y_true == 1)).sum())
        prec = tp / k if k else 0.0
        rec = tp / max(int(y_true.sum()), 1)
        rows.append(
            {
                "capacity": cap,
                "n_flagged": k,
                "precision": prec,
                "recall": rec,
                "threshold": float(proba[flagged[-1]]),
            }
        )
    return pd.DataFrame(rows)


def evaluate_predictions(
    y_true: np.ndarray,
    proba: np.ndarray,
    *,
    seed: int = 42,
) -> dict[str, Any]:
    metrics = classification_metrics(y_true, proba)
    ci = bootstrap_metrics(y_true, proba, seed=seed)
    capacity = threshold_capacity_table(y_true, proba)
    # also recall-target thresholds
    prec, rec, thresh = precision_recall_curve(y_true, proba)
    recall_rows = []
    for target in (0.6, 0.7, 0.8):
        idx = int(np.argmin(np.abs(rec - target)))
        recall_rows.append(
            {
                "target_recall": target,
                "actual_recall": float(rec[idx]),
                "precision": float(prec[idx]),
                "threshold": float(thresh[idx]) if idx < len(thresh) else 1.0,
            }
        )
    logger.info("Eval metrics: %s", metrics)
    return {
        "metrics": metrics,
        "bootstrap": ci,
        "capacity_table": capacity.to_dict(orient="records"),
        "recall_targets": recall_rows,
    }
