#!/usr/bin/env python3
"""
Daily decision-evaluation DAG (local-first).

Reconciles ledger rows and writes a summary JSON. Optional Airflow DAG when installed.
Does not auto-promote or change policy.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

dag = None  # type: ignore[assignment]

DEFAULT_LEDGER = Path("artifacts/decision_ledger.jsonl")
DEFAULT_OUT = Path("artifacts/decision_eval_report.json")


def run_decision_evaluation(
    ledger_path: Path = DEFAULT_LEDGER,
    output_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if ledger_path.exists():
        with ledger_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

    by_type = Counter(r.get("record_type") for r in rows)
    actions = [r for r in rows if r.get("record_type") == "action"]
    spend = sum(float(r.get("simulated_cost") or 0.0) for r in actions)
    net = sum(float(r.get("simulated_net_value") or 0.0) for r in actions)
    action_dist = Counter(r.get("action_type") for r in actions)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "ledger_path": str(ledger_path),
        "record_counts": dict(by_type),
        "interventions": len([a for a in actions if a.get("action_type") != "NO_ACTION"]),
        "intervention_spend_simulated": spend,
        "net_value_simulated": net,
        "action_distribution": dict(action_dist),
        "note": "Simulated financials only; not causal ROI.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    def _task(**_context: Any) -> dict[str, Any]:
        return run_decision_evaluation()

    with DAG(
        dag_id="olist_daily_decision_evaluation",
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        tags=["olist", "decision"],
    ) as dag:
        PythonOperator(task_id="evaluate_decisions", python_callable=_task)
except ImportError:
    dag = None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    report = run_decision_evaluation(args.ledger, args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
