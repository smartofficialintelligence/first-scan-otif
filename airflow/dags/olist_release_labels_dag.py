#!/usr/bin/env python3
"""Release delayed labels where virtual_now >= label_release_at."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from olist_ml.monitoring.labels import run_release_labels  # noqa: E402

dag = None  # type: ignore[assignment]
DEFAULT_LOG = Path("artifacts/prediction_logs.jsonl")


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def run_release_labels_task(
    *,
    log_path: Path = DEFAULT_LOG,
    virtual_now: datetime | None = None,
) -> dict[str, Any]:
    now = virtual_now or _parse_now(os.environ.get("LABEL_VIRTUAL_NOW"))
    return run_release_labels(log_path=log_path, virtual_now=now)


try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    def _task(**_context: Any) -> dict[str, Any]:
        return run_release_labels_task()

    with DAG(
        dag_id="olist_release_labels",
        description="Mark delayed labels released (prediction_ts + 7d)",
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        tags=["olist", "labels", "m10"],
    ) as dag:
        PythonOperator(task_id="release_labels", python_callable=_task)
except ImportError:
    dag = None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local label release (no Composer)")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--virtual-now", default=None)
    args = parser.parse_args(argv)
    result = run_release_labels_task(
        log_path=args.log_path,
        virtual_now=_parse_now(args.virtual_now),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
