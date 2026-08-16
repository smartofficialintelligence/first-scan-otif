"""Optuna hyperparameter search for XGBoost (PR-AUC)."""

from __future__ import annotations

import numpy as np
import optuna
import xgboost as xgb
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedKFold

from olist_ml.logging import get_logger

logger = get_logger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


def tune_xgboost(
    X: np.ndarray,
    y: np.ndarray,
    *,
    n_trials: int = 10,
    cv_folds: int = 3,
    seed: int = 42,
) -> optuna.Study:
    pos = max(int((y == 1).sum()), 1)
    neg = max(int((y == 0).sum()), 1)
    spw = neg / pos

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 80, 400),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "gamma": trial.suggest_float("gamma", 0.0, 3.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 3.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.0, 3.0),
            "scale_pos_weight": spw,
            "objective": "binary:logistic",
            "eval_metric": "aucpr",
            "random_state": seed,
            "n_jobs": 2,
            "verbosity": 0,
        }
        cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
        scores: list[float] = []
        for tr_idx, va_idx in cv.split(X, y):
            model = xgb.XGBClassifier(**params)
            model.fit(X[tr_idx], y[tr_idx])
            proba = model.predict_proba(X[va_idx])[:, 1]
            scores.append(float(average_precision_score(y[va_idx], proba)))
        return float(np.mean(scores))

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    logger.info("Optuna best PR-AUC=%.4f params=%s", study.best_value, study.best_params)
    return study
