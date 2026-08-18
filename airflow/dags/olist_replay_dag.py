#!/usr/bin/env python3
"""Replay holdout through PredictionService (local-first; optional Airflow)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

dag = None  # type: ignore[assignment]


def _load_replay_module() -> Any:
    path = ROOT / "scripts" / "replay_traffic.py"
    spec = importlib.util.spec_from_file_location("replay_traffic", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_replay_canary(
    *,
    scenario: str = "baseline",
    snapshot_id: str = "local-fixtures",
    seed: int = 42,
    no_challenger: bool = True,
) -> dict[str, Any]:
    replay = _load_replay_module()
    log_path = replay.run_replay(
        scenario=scenario,
        snapshot_id=snapshot_id,
        seed=seed,
        use_challenger=not no_challenger,
        challenger_model=None if no_challenger else Path("artifacts/model_challenger_bad.joblib"),
    )
    return {
        "scenario": scenario,
        "snapshot_id": snapshot_id,
        "seed": seed,
        "log_path": str(log_path),
        "auto_promote": False,
    }


try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    def _task(**_context: Any) -> dict[str, Any]:
        return run_replay_canary()

    with DAG(
        dag_id="olist_replay_canary",
        description="Replay holdout traffic into prediction logs",
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        tags=["olist", "replay", "m10"],
    ) as dag:
        PythonOperator(task_id="replay_canary", python_callable=_task)
except ImportError:
    dag = None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local replay_canary (no Composer)")
    parser.add_argument("--scenario", default="baseline")
    parser.add_argument("--snapshot-id", default="local-fixtures")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--with-challenger", action="store_true")
    args = parser.parse_args(argv)
    result = run_replay_canary(
        scenario=args.scenario,
        snapshot_id=args.snapshot_id,
        seed=args.seed,
        no_challenger=not args.with_challenger,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
