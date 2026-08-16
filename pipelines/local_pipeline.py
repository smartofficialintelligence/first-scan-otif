"""Local orchestrator: validate → train steps → register MLflow candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from olist_ml.logging import get_logger, setup_logging
from pipelines.components import register_candidate, run_train_steps, validate_data

logger = get_logger(__name__)


def run_pipeline(
    data_dir: Path | str = "data/fixtures",
    *,
    trials: int = 3,
    tracking_uri: str | None = None,
) -> dict[str, Any]:
    """
    Pipeline steps:
    validate → tune → train → calibrate → evaluate → log MLflow → register candidate.

    Lifecycle stops at REGISTERED_CANDIDATE (no auto-promote).
    """
    setup_logging()
    data_dir = Path(data_dir)
    validation = validate_data(data_dir)
    meta = run_train_steps(data_dir, trials=trials)
    run_id = register_candidate(meta, tracking_uri=tracking_uri)
    result = {
        "validation": {"ok": validation["ok"], "data_dir": validation["data_dir"]},
        "model_version": meta.model_version,
        "metrics": meta.metrics,
        "mlflow_run_id": run_id,
        "lifecycle_state": "REGISTERED_CANDIDATE",
    }
    logger.info("Local pipeline complete: %s", json.dumps(result, default=str))
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Local training pipeline (validate → train → MLflow candidate)"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/fixtures"))
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument(
        "--tracking-uri",
        type=str,
        default=None,
        help="MLflow tracking URI (default: MLFLOW_TRACKING_URI or file:./artifacts/mlruns)",
    )
    args = parser.parse_args(argv)
    run_pipeline(args.data_dir, trials=args.trials, tracking_uri=args.tracking_uri)


if __name__ == "__main__":
    main()
