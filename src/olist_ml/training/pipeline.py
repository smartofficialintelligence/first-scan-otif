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
from olist_ml.features.contracts import FEATURE_COLUMNS
from olist_ml.logging import get_logger, setup_logging
from olist_ml.training.evaluate import evaluate_predictions
from olist_ml.training.package import ModelMeta, new_model_version, save_artifact
from olist_ml.training.train import train_model_bundle
from olist_ml.training.tune import tune_xgboost

logger = get_logger(__name__)


def run_training(settings: Settings, data_dir: Path | None = None) -> ModelMeta:
    setup_logging(settings.log_level)
    root = data_dir or settings.data_dir
    tables = load_olist_tables(root)
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled)

    splits = temporal_split(
        features,
        valid_fraction=settings.valid_fraction,
        test_fraction=settings.test_fraction,
        replay_fraction=settings.replay_fraction,
    )
    train_df = splits.train
    valid_df = splits.validation if len(splits.validation) else train_df
    test_df = splits.test if len(splits.test) else valid_df

    X_train_df = select_feature_frame(train_df)
    y_train = train_df["late_delivery"].to_numpy()
    X_valid_df = select_feature_frame(valid_df)
    y_valid = valid_df["late_delivery"].to_numpy()
    X_test_df = select_feature_frame(test_df)
    y_test = test_df["late_delivery"].to_numpy()

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
        X_df_valid=X_valid_df,
        y_valid=y_valid,
    )

    valid_report = evaluate_predictions(
        y_valid, bundle.predict_proba(X_valid_df)[:, 1], seed=settings.random_seed
    )
    test_report = evaluate_predictions(
        y_test, bundle.predict_proba(X_test_df)[:, 1], seed=settings.random_seed
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
        },
        n_train=len(train_df),
        n_valid=len(valid_df),
        n_test=len(test_df),
    )

    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    save_artifact(bundle, meta, model_path=settings.model_path, meta_path=settings.model_meta_path)

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
    logger.info(
        "Training complete model_version=%s test_pr_auc=%.4f",
        version,
        test_report["metrics"]["pr_auc"],
    )
    return meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train local Olist late-delivery model")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--trials", type=int, default=None)
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.trials is not None:
        settings.n_optuna_trials = args.trials
    run_training(settings, data_dir=args.data_dir)


if __name__ == "__main__":
    main()
