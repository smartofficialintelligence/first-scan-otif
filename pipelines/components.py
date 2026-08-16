"""Plain Python pipeline step functions (no live Vertex required)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from olist_ml.config import Settings, get_settings
from olist_ml.data.loaders import REQUIRED_FILES, load_olist_tables, table_summary
from olist_ml.logging import get_logger
from olist_ml.registry.mlflow_registry import log_and_register_candidate
from olist_ml.training.gates import offline_promotion_checks
from olist_ml.training.package import ModelMeta
from olist_ml.training.pipeline import run_training

logger = get_logger(__name__)


def validate_data(data_dir: Path | str) -> dict[str, Any]:
    """Validate required Olist CSVs exist and are loadable."""
    root = Path(data_dir)
    missing = [name for name in REQUIRED_FILES.values() if not (root / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing data files under {root}: {missing}")
    tables = load_olist_tables(root)
    summary = table_summary(tables)
    empty = [name for name, info in summary.items() if info["rows"] == 0]
    if empty:
        raise ValueError(f"Empty tables: {empty}")
    logger.info("Validated data_dir=%s tables=%s", root, list(summary))
    return {"ok": True, "data_dir": str(root), "summary": summary}


def run_train_steps(
    data_dir: Path | str,
    *,
    trials: int | None = None,
    settings: Settings | None = None,
) -> ModelMeta:
    """
    Tune → train → calibrate → evaluate via existing ``run_training``.

    Lifecycle conceptually moves TRAINED → EVALUATED once metrics are on ModelMeta.
    """
    cfg = settings or get_settings()
    if trials is not None:
        cfg.n_optuna_trials = trials
    meta = run_training(cfg, data_dir=Path(data_dir))
    logger.info(
        "Train steps complete version=%s metrics_keys=%s",
        meta.model_version,
        list(meta.metrics),
    )
    return meta


def register_candidate(
    meta: ModelMeta,
    *,
    model_path: Path | str | None = None,
    meta_path: Path | str | None = None,
    tracking_uri: str | None = None,
    champion_metrics: dict[str, Any] | None = None,
    enforce_gates: bool = False,
) -> str:
    """
    Log MLflow run and register ``olist-late-delivery`` as REGISTERED_CANDIDATE.

    Does not auto-promote past human gates. Optional ``enforce_gates`` runs
    offline_promotion_checks and raises if they fail.
    """
    cfg = get_settings()
    model_p = Path(model_path) if model_path else cfg.model_path
    meta_p = Path(meta_path) if meta_path else cfg.model_meta_path

    if enforce_gates:
        gate = offline_promotion_checks(meta.metrics, champion_metrics)
        if not gate["passed"]:
            raise RuntimeError(f"Offline promotion checks failed: {gate['reasons']}")

    run_id = log_and_register_candidate(
        meta,
        model_p,
        meta_p,
        tracking_uri=tracking_uri,
    )
    logger.info("Candidate registered run_id=%s (lifecycle=REGISTERED_CANDIDATE)", run_id)
    return run_id
