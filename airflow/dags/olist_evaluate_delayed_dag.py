#!/usr/bin/env python3
"""Delayed-label quality eval (released rows only)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from olist_ml.monitoring.delayed_eval import (  # noqa: E402
    DEFAULT_LOG,
    DEFAULT_OUT,
    run_evaluate_delayed,
)

dag = None  # type: ignore[assignment]


def run_evaluate_delayed_task(
    *,
    log_path: Path = DEFAULT_LOG,
    out_path: Path = DEFAULT_OUT,
    baseline_pr_auc: float | None = None,
    champion_pr_auc: float | None = None,
) -> dict[str, Any]:
    return run_evaluate_delayed(
        log_path=log_path,
        out_path=out_path,
        baseline_pr_auc=baseline_pr_auc,
        champion_pr_auc=champion_pr_auc,
    )


try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    def _task(**_context: Any) -> dict[str, Any]:
        # Loads baseline/champion PR-AUC from artifacts/model_meta.json when unset.
        return run_evaluate_delayed_task()

    with DAG(
        dag_id="olist_evaluate_delayed",
        description="PR-AUC / Brier on released labels only; quality alarm; no deploy",
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        tags=["olist", "quality", "m10"],
    ) as dag:
        PythonOperator(task_id="evaluate_delayed", python_callable=_task)
except ImportError:
    dag = None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local delayed-label eval (no Composer)")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--baseline-pr-auc", type=float, default=None)
    parser.add_argument("--champion-pr-auc", type=float, default=None)
    args = parser.parse_args(argv)
    report = run_evaluate_delayed_task(
        log_path=args.log_path,
        out_path=args.out,
        baseline_pr_auc=args.baseline_pr_auc,
        champion_pr_auc=args.champion_pr_auc,
    )
    print(json.dumps(report, indent=2, default=str))
    if report.get("quality_alarm"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
