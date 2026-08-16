#!/usr/bin/env python3
"""
Olist training trigger DAG.

When Airflow is installed (Composer), defines a real DAG.
Otherwise ``dag = None`` and ``run_train_trigger()`` runs the local pipeline
without Composer (see ``make airflow-train-local``).

Human gates H5 (retrain approval) and H6 (promote) remain required — this DAG
only produces a REGISTERED_CANDIDATE. No auto-promote.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Local execution (no Composer)
# ---------------------------------------------------------------------------


def run_train_trigger(
    data_dir: str | Path = "data/fixtures",
    *,
    trials: int = 3,
    tracking_uri: str | None = None,
) -> dict[str, Any]:
    """
    Call ``pipelines.local_pipeline.run_pipeline`` / training path.

    Lifecycle stops at REGISTERED_CANDIDATE — H5/H6 still required before promote.
    """
    from pipelines.local_pipeline import run_pipeline

    result = run_pipeline(Path(data_dir), trials=trials, tracking_uri=tracking_uri)
    result["human_gates"] = {
        "H5_retrain_approval": "required before scheduled/alarm-driven retrain in prod",
        "H6_promote": "required before champion swap — never auto-promote",
    }
    result["auto_promote"] = False
    return result


# ---------------------------------------------------------------------------
# Optional Airflow DAG
# ---------------------------------------------------------------------------

dag = None  # type: ignore[assignment]

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    def _train_task(**_context: Any) -> dict[str, Any]:
        return run_train_trigger()

    with DAG(
        dag_id="olist_train",
        description="Trigger Olist training → MLflow REGISTERED_CANDIDATE (no auto-promote)",
        start_date=datetime(2024, 1, 1),
        schedule=None,  # manual / external trigger; H5 before enable
        catchup=False,
        tags=["olist", "train", "m10"],
    ) as dag:
        PythonOperator(
            task_id="run_train_trigger",
            python_callable=_train_task,
        )
except ImportError:
    dag = None


def main(argv: list[str] | None = None) -> None:
    import json

    parser = argparse.ArgumentParser(description="Local Airflow train trigger (no Composer)")
    parser.add_argument("--local", action="store_true", help="Run run_train_trigger locally")
    parser.add_argument("--data-dir", type=Path, default=Path("data/fixtures"))
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args(argv)
    # Script entrypoint always runs locally (Composer imports the module for ``dag``).
    result = run_train_trigger(args.data_dir, trials=args.trials)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
