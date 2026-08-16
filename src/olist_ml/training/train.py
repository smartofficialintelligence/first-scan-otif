"""Train calibrated XGBoost classifier."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV

from olist_ml.features.assembler import make_preprocessor
from olist_ml.logging import get_logger

logger = get_logger(__name__)


class ModelBundle:
    """Fitted preprocessor + model with a stable predict_proba(DataFrame) API."""

    def __init__(self, preprocessor: Any, model: Any) -> None:
        self.preprocessor = preprocessor
        self.model = model

    def predict_proba(self, X_df: pd.DataFrame) -> np.ndarray:
        Xt = self.preprocessor.transform(X_df)
        return self.model.predict_proba(Xt)

    def predict(self, X_df: pd.DataFrame) -> np.ndarray:
        Xt = self.preprocessor.transform(X_df)
        return self.model.predict(Xt)


def build_xgb_params(
    best_params: dict[str, Any],
    *,
    y_train: np.ndarray,
    seed: int,
) -> dict[str, Any]:
    pos = max(int((y_train == 1).sum()), 1)
    neg = max(int((y_train == 0).sum()), 1)
    params = dict(best_params)
    params.update(
        {
            "scale_pos_weight": neg / pos,
            "objective": "binary:logistic",
            "eval_metric": "aucpr",
            "random_state": seed,
            "n_jobs": 2,
            "verbosity": 0,
        }
    )
    return params


def train_calibrated_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    best_params: dict[str, Any],
    seed: int = 42,
    calibrate: bool = True,
) -> CalibratedClassifierCV | xgb.XGBClassifier:
    params = build_xgb_params(best_params, y_train=y_train, seed=seed)
    base = xgb.XGBClassifier(**params)
    if not calibrate or len(np.unique(y_train)) < 2 or len(y_train) < 30:
        logger.warning("Skipping calibration (insufficient data or disabled)")
        base.fit(X_train, y_train)
        return base

    calibrated = CalibratedClassifierCV(base, method="isotonic", cv=3)
    calibrated.fit(X_train, y_train)
    logger.info("Trained calibrated XGBoost on %s rows", f"{len(y_train):,}")
    return calibrated


def train_model_bundle(
    X_df_train: pd.DataFrame,
    y_train: np.ndarray,
    *,
    best_params: dict[str, Any],
    seed: int = 42,
) -> ModelBundle:
    pre = make_preprocessor()
    X_tr = pre.fit_transform(X_df_train)
    model = train_calibrated_model(X_tr, y_train, best_params=best_params, seed=seed)
    return ModelBundle(pre, model)
