"""Optuna hyperparameter search for XGBoost (PR-AUC) with temporal CV."""

from __future__ import annotations

import numpy as np
import optuna
import xgboost as xgb
from sklearn.metrics import average_precision_score
from sklearn.model_selection import TimeSeriesSplit

from olist_ml.logging import get_logger

logger = get_logger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


def tune_xgboost(
    X: np.ndarray,
    y: np.ndarray,
    *,
    n_trials: int = 25,
    cv_folds: int = 3,
    seed: int = 42,
) -> optuna.Study:
    """Maximize mean PR-AUC under TimeSeriesSplit (rows must be time-ordered)."""
    pos = max(int((y == 1).sum()), 1)
    neg = max(int((y == 0).sum()), 1)
    spw = neg / pos

    n_splits = max(2, min(cv_folds, len(y) // 5 if len(y) >= 10 else 2))
    # Keep enough positives in later folds when possible.
    while n_splits > 2:
        tscv = TimeSeriesSplit(n_splits=n_splits)
        ok = True
        for _, va_idx in tscv.split(X):
            if int(y[va_idx].sum()) < 1 or int((1 - y[va_idx]).sum()) < 1:
                ok = False
                break
        if ok:
            break
        n_splits -= 1

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 100, 600),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "subsample": trial.suggest_float("subsample", 0.55, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.55, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
            "gamma": trial.suggest_float("gamma", 0.0, 5.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "scale_pos_weight": spw,
            "objective": "binary:logistic",
            "eval_metric": "aucpr",
            "random_state": seed,
            "n_jobs": 2,
            "verbosity": 0,
        }
        cv = TimeSeriesSplit(n_splits=n_splits)
        scores: list[float] = []
        for tr_idx, va_idx in cv.split(X):
            if len(np.unique(y[tr_idx])) < 2 or len(np.unique(y[va_idx])) < 2:
                continue
            model = xgb.XGBClassifier(**params)
            model.fit(X[tr_idx], y[tr_idx])
            proba = model.predict_proba(X[va_idx])[:, 1]
            scores.append(float(average_precision_score(y[va_idx], proba)))
        if not scores:
            return 0.0
        return float(np.mean(scores))

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    logger.info(
        "Optuna best PR-AUC=%.4f (temporal folds=%s) params=%s",
        study.best_value,
        n_splits,
        study.best_params,
    )
    return study
