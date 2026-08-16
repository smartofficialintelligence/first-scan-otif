"""Train calibrated XGBoost classifier."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator

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
    early_stopping_rounds: int | None = 50,
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
    if early_stopping_rounds is not None:
        params["early_stopping_rounds"] = early_stopping_rounds
    return params


def train_calibrated_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    *,
    best_params: dict[str, Any],
    seed: int = 42,
    calibrate: bool = True,
    X_valid: np.ndarray | None = None,
    y_valid: np.ndarray | None = None,
) -> CalibratedClassifierCV | xgb.XGBClassifier:
    use_valid = (
        X_valid is not None
        and y_valid is not None
        and len(y_valid) >= 20
        and len(np.unique(y_valid)) >= 2
    )
    params = build_xgb_params(
        best_params,
        y_train=y_train,
        seed=seed,
        early_stopping_rounds=50 if use_valid else None,
    )
    base = xgb.XGBClassifier(**params)
    if use_valid:
        base.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)
        logger.info(
            "Fitted XGBoost with early stopping; best_iteration=%s",
            getattr(base, "best_iteration", None),
        )
    else:
        params.pop("early_stopping_rounds", None)
        base = xgb.XGBClassifier(**params)
        base.fit(X_train, y_train)

    if not calibrate:
        return base

    if use_valid:
        calibrated = CalibratedClassifierCV(FrozenEstimator(base), method="isotonic")
        calibrated.fit(X_valid, y_valid)
        logger.info(
            "Trained XGBoost + held-out isotonic calibration (train=%s valid=%s)",
            f"{len(y_train):,}",
            f"{len(y_valid):,}",
        )
        return calibrated

    if len(np.unique(y_train)) < 2 or len(y_train) < 30:
        logger.warning("Skipping calibration (insufficient data)")
        return base

    calibrated = CalibratedClassifierCV(
        xgb.XGBClassifier(
            **build_xgb_params(
                best_params, y_train=y_train, seed=seed, early_stopping_rounds=None
            )
        ),
        method="isotonic",
        cv=3,
    )
    calibrated.fit(X_train, y_train)
    logger.info("Trained CV-calibrated XGBoost on %s rows", f"{len(y_train):,}")
    return calibrated


def train_model_bundle(
    X_df_train: pd.DataFrame,
    y_train: np.ndarray,
    *,
    best_params: dict[str, Any],
    seed: int = 42,
    X_df_valid: pd.DataFrame | None = None,
    y_valid: np.ndarray | None = None,
) -> ModelBundle:
    pre = make_preprocessor()
    X_tr = pre.fit_transform(X_df_train)
    X_va = pre.transform(X_df_valid) if X_df_valid is not None else None
    model = train_calibrated_model(
        X_tr,
        y_train,
        best_params=best_params,
        seed=seed,
        X_valid=X_va,
        y_valid=y_valid,
    )
    return ModelBundle(pre, model)
