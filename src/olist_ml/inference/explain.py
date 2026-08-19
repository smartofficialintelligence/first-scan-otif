"""Tree SHAP for a single scoring request.

Explains the XGBoost booster **before** isotonic calibration. The API still
returns the calibrated `promise_miss_probability` used by policy.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from olist_ml.logging import get_logger
from olist_ml.schemas import TopFeatureContribution

logger = get_logger(__name__)

SHAP_NOTE = (
    "Tree SHAP on the XGBoost booster before isotonic calibration. "
    "Values are additive contributions to the tree output (not the calibrated "
    "probability). Displayed promise_miss_probability remains the calibrated "
    "score used for policy."
)

STUB_NOTE = (
    "Could not run Tree SHAP on this artifact; returning feature names with "
    "zero contributions."
)


def unwrap_xgb_classifier(model: Any) -> Any | None:
    """Walk CalibratedClassifierCV / FrozenEstimator to the fitted XGBClassifier.

    FrozenEstimator forwards ``get_booster`` / ``predict_proba``, so duck-typing
    those attributes is not enough — TreeExplainer rejects the wrapper.
    """
    import xgboost as xgb

    current = model
    for _ in range(8):
        if current is None:
            return None
        if isinstance(current, xgb.XGBClassifier):
            return current
        if getattr(current, "calibrated_classifiers_", None):
            current = current.calibrated_classifiers_[0]
            continue
        inner = getattr(current, "estimator", None)
        if inner is not None and inner is not current:
            current = inner
            continue
        return None
    return None


def display_feature_name(name: str) -> str:
    if name.startswith("num__") or name.startswith("cat__"):
        return name[5:]
    return name


def _positive_shap_row(raw: Any) -> np.ndarray:
    if isinstance(raw, list):
        raw = raw[-1]
    if hasattr(raw, "values"):
        raw = raw.values
    arr = np.asarray(raw)
    if arr.ndim == 3:
        arr = arr[:, :, -1]
    if arr.ndim == 2:
        return arr[0]
    if arr.ndim == 1:
        return arr
    raise ValueError(f"Unexpected SHAP shape {arr.shape}")


def tree_shap_top_features(
    xgb_clf: Any,
    xt: np.ndarray,
    feature_names: list[str],
    *,
    top_k: int = 10,
    explainer: Any | None = None,
) -> tuple[list[TopFeatureContribution], Any]:
    """Return top-|SHAP| features for one transformed row and the cached explainer."""
    import shap

    if explainer is None:
        booster = xgb_clf.get_booster() if hasattr(xgb_clf, "get_booster") else xgb_clf
        explainer = shap.TreeExplainer(booster)
    values = _positive_shap_row(explainer.shap_values(xt))
    if len(values) != len(feature_names):
        names = [f"f{i}" for i in range(len(values))]
    else:
        names = feature_names
    ranked = sorted(
        zip(names, values.tolist(), strict=True),
        key=lambda item: abs(float(item[1])),
        reverse=True,
    )
    top = [
        TopFeatureContribution(feature=display_feature_name(name), contribution=float(value))
        for name, value in ranked[:top_k]
    ]
    return top, explainer
