#!/usr/bin/env python3
"""
Olist drift-check DAG.

Feature PSI (seller late rates, geo, online seller counts) plus high-band mix
shift. Writes ``artifacts/drift_alarm.json``. Does **not** train or deploy.

Alarm is not a retrain: ``olist_retrain`` reads the alarm + H5 flag.
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

from olist_ml.monitoring.drift import (  # noqa: E402
    DEFAULT_ALARM,
    DEFAULT_LOG,
    resolve_baseline_log,
    run_drift_check,
)

dag = None  # type: ignore[assignment]


try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    def _drift_task(**_context: Any) -> dict[str, Any]:
        return run_drift_check(baseline_log_path=resolve_baseline_log())

    with DAG(
        dag_id="olist_drift",
        description="Feature PSI + high-band mix; alarm only (no deploy)",
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        tags=["olist", "drift", "m10"],
    ) as dag:
        PythonOperator(
            task_id="run_drift_check",
            python_callable=_drift_task,
        )
except ImportError:
    dag = None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local drift check (no Composer)")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--baseline-log", type=Path, default=None)
    parser.add_argument("--alarm-path", type=Path, default=DEFAULT_ALARM)
    args = parser.parse_args(argv)
    result = run_drift_check(
        log_path=args.log_path,
        baseline_log_path=resolve_baseline_log(args.baseline_log),
        alarm_path=args.alarm_path,
    )
    print(json.dumps(result, indent=2, default=str))
    if result.get("alarm"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
