"""End-to-end local training pipeline CLI."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from olist_ml.config import Settings, get_settings
from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.splits import temporal_split
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.assembler import make_preprocessor, select_feature_frame
from olist_ml.features.build import build_feature_table
from olist_ml.features.contracts import FEATURE_COLUMNS, TARGET_COLUMN, TARGET_NAME
from olist_ml.features.historical import apply_warehouse_features
from olist_ml.gitinfo import current_git_sha
from olist_ml.logging import get_logger, setup_logging
from olist_ml.training.evaluate import evaluate_predictions, score_capacity_thresholds
from olist_ml.training.package import ModelMeta, new_model_version, save_artifact
from olist_ml.training.promote import candidate_paths
from olist_ml.training.train import train_model_bundle
from olist_ml.training.tune import tune_xgboost

logger = get_logger(__name__)


def run_training(
    settings: Settings,
    data_dir: Path | None = None,
    *,
    register_mlflow: bool = True,
) -> ModelMeta:
    setup_logging(settings.log_level)
    root = data_dir or settings.data_dir
    tables = load_olist_tables(root)
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled)

    # dbt snapshot / Feast historical feed the champion when they exist, so the
    # warehouse is an input rather than an unused export. Falls back to pandas.
    warehouse = apply_warehouse_features(features, settings)
    features = warehouse.frame

    splits = temporal_split(
        features,
        time_col="handoff_ts",
        valid_fraction=settings.valid_fraction,
        test_fraction=settings.test_fraction,
        replay_fraction=settings.replay_fraction,
    )
    train_df = splits.train
    valid_df = splits.validation if len(splits.validation) else train_df
    test_df = splits.test if len(splits.test) else valid_df

    # The validation window is split so no slice does triple duty: the earlier
    # half (calibration) fits early stopping + isotonic; the later half
    # (threshold) is untouched by any fitting and freezes P1/P2 cutoffs and
    # the reported validation metrics. Tiny fixture runs cannot split.
    if len(valid_df) >= 40:
        cal_cut = len(valid_df) // 2
        cal_df = valid_df.iloc[:cal_cut]
        thr_df = valid_df.iloc[cal_cut:]
    else:
        cal_df = valid_df
        thr_df = valid_df

    X_train_df = select_feature_frame(train_df)
    y_train = train_df[TARGET_COLUMN].to_numpy()
    X_cal_df = select_feature_frame(cal_df)
    y_cal = cal_df[TARGET_COLUMN].to_numpy()
    X_thr_df = select_feature_frame(thr_df)
    y_thr = thr_df[TARGET_COLUMN].to_numpy()
    X_test_df = select_feature_frame(test_df)
    y_test = test_df[TARGET_COLUMN].to_numpy()

    pre = make_preprocessor()
    X_tr = pre.fit_transform(X_train_df)
    n_folds = min(settings.cv_folds, max(2, int(y_train.sum()), int((1 - y_train).sum())))
    n_folds = max(2, min(n_folds, len(y_train) // 5 if len(y_train) >= 10 else 2))
    study = tune_xgboost(
        X_tr,
        y_train,
        n_trials=settings.n_optuna_trials,
        cv_folds=n_folds,
        seed=settings.random_seed,
    )

    bundle = train_model_bundle(
        X_train_df,
        y_train,
        best_params=study.best_params,
        seed=settings.random_seed,
        X_df_valid=X_cal_df,
        y_valid=y_cal,
    )

    thr_proba = bundle.predict_proba(X_thr_df)[:, 1]
    test_proba = bundle.predict_proba(X_test_df)[:, 1]
    valid_report = evaluate_predictions(y_thr, thr_proba, seed=settings.random_seed)
    test_report = evaluate_predictions(y_test, test_proba, seed=settings.random_seed)
    p1_capacity = 0.025
    p2_capacity = 0.10
    p1_score_threshold, p2_score_threshold = score_capacity_thresholds(
        thr_proba, p1_capacity=p1_capacity, p2_capacity=p2_capacity
    )

    version = new_model_version("local")
    meta = ModelMeta(
        model_version=version,
        trained_at=datetime.now(UTC).isoformat(),
        feature_names=FEATURE_COLUMNS,
        best_params=study.best_params,
        metrics={
            **{f"valid_{k}": v for k, v in valid_report["metrics"].items()},
            **{f"test_{k}": v for k, v in test_report["metrics"].items()},
            "best_cv_pr_auc": float(study.best_value),
            "p1_score_threshold": p1_score_threshold,
            "p2_score_threshold": p2_score_threshold,
            "n_calibration": float(len(cal_df)),
            "n_threshold": float(len(thr_df)),
            "warehouse_overlay_rows": float(warehouse.overlay_rows),
        },
        git_sha=current_git_sha(),
        snapshot_id=warehouse.snapshot_id,
        n_train=len(train_df),
        n_valid=len(valid_df),
        n_test=len(test_df),
        target=TARGET_NAME,
        p1_score_threshold=p1_score_threshold,
        p2_score_threshold=p2_score_threshold,
        p1_capacity=p1_capacity,
        p2_capacity=p2_capacity,
    )

    # Candidates never land on the champion path (settings.model_path) —
    # that swap is an explicit human promote (scripts/promote_candidate.py, H6).
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    cand_model, cand_meta = candidate_paths(settings, version)
    save_artifact(bundle, meta, model_path=cand_model, meta_path=cand_meta)

    report_path = settings.artifact_dir / "eval_report.json"
    report_path.write_text(
        json.dumps(
            {
                "validation": valid_report,
                "test": test_report,
                "cutoffs": {k: str(v) for k, v in splits.cutoffs.items()},
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    replay_csv = settings.artifact_dir / "replay_holdout.csv"
    splits.replay_holdout.to_csv(replay_csv, index=False)

    if register_mlflow:
        run_id = register_training_run(meta, cand_model, cand_meta, settings)
        logger.info("MLflow candidate registered run_id=%s", run_id)

    logger.info(
        "Training complete model_version=%s test_pr_auc=%.4f snapshot=%s",
        version,
        test_report["metrics"]["pr_auc"],
        meta.snapshot_id,
    )
    return meta


def mlflow_tracking_uri(settings: Settings) -> str:
    """Tracking store beside the artifacts it describes (tests get a tmp dir)."""
    return f"sqlite:///{(settings.artifact_dir / 'mlflow.db').resolve()}"


def register_training_run(
    meta: ModelMeta,
    model_path: Path,
    meta_path: Path,
    settings: Settings,
) -> str:
    """Log this run to MLflow and tag it REGISTERED_CANDIDATE.

    Every champion now has registry lineage — ``make train-local`` used to skip
    MLflow entirely, so the deployed model had no run behind it. A missing
    ``ml`` extra raises rather than silently skipping: a candidate that never
    reached the registry must not look like one that did.
    """
    try:
        from olist_ml.registry.mlflow_registry import log_and_register_candidate
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise RuntimeError(
            "MLflow is required to register a training run. Install the extra "
            "(`uv sync --extra ml`) or call run_training(register_mlflow=False)."
        ) from exc

    return log_and_register_candidate(
        meta,
        model_path,
        meta_path,
        tracking_uri=mlflow_tracking_uri(settings),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train local Olist promise-miss (handoff) model")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--trials", type=int, default=None)
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.trials is not None:
        settings.n_optuna_trials = args.trials
    run_training(settings, data_dir=args.data_dir)


if __name__ == "__main__":
    main()
