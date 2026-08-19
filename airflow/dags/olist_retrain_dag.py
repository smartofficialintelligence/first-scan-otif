#!/usr/bin/env python3
"""
Retrain trigger DAG.

Reads drift_alarm.json (when reason=drift) and requires H5 approval before
calling the local/Vertex training pipeline. Monthly schedule still needs H5.
Never auto-promotes.

``make airflow-train-local`` remains unconstrained for M4 demos — this DAG is
the contract path (alarm → H5 → candidate).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from olist_ml.monitoring.h5 import assert_retrain_allowed  # noqa: E402

dag = None  # type: ignore[assignment]


def run_retrain_trigger(
    *,
    reason: str = "drift",
    data_dir: str | Path = "data/fixtures",
    trials: int = 3,
    tracking_uri: str | None = None,
    require_h5: bool = True,
) -> dict[str, Any]:
    assert_retrain_allowed(reason=reason, require_h5=require_h5)
    from pipelines.local_pipeline import run_pipeline

    # Governance path enforces offline gates vs the current champion; a worse
    # candidate is rejected here, not at some later human step.
    result = run_pipeline(
        Path(data_dir), trials=trials, tracking_uri=tracking_uri, enforce_gates=True
    )
    result["retrain_reason"] = reason
    result["human_gates"] = {
        "H5_retrain_approval": "required — this trigger checked the H5 flag",
        "H6_promote": "required before champion swap — never auto-promote",
    }
    result["auto_promote"] = False
    result["lifecycle_state"] = "REGISTERED_CANDIDATE"
    return result


try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    def _task(**_context: Any) -> dict[str, Any]:
        return run_retrain_trigger(reason="monthly")

    with DAG(
        dag_id="olist_retrain",
        description="H5-gated retrain → REGISTERED_CANDIDATE (monthly or drift)",
        start_date=datetime(2024, 1, 1),
        schedule="0 0 1 * *",
        catchup=False,
        tags=["olist", "retrain", "m10"],
    ) as dag:
        PythonOperator(task_id="retrain_trigger", python_callable=_task)
except ImportError:
    dag = None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local retrain_trigger (H5 required)")
    parser.add_argument("--reason", default="drift", choices=["drift", "monthly", "manual"])
    parser.add_argument("--data-dir", type=Path, default=Path("data/fixtures"))
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument(
        "--skip-h5",
        action="store_true",
        help="Forbidden in prod; only for isolating pipeline errors",
    )
    args = parser.parse_args(argv)
    result = run_retrain_trigger(
        reason=args.reason,
        data_dir=args.data_dir,
        trials=args.trials,
        require_h5=not args.skip_h5,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
