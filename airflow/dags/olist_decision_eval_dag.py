#!/usr/bin/env python3
"""
Daily decision-evaluation DAG (local-first).

Reconciles ledger rows and writes a simulated business-outcome summary.
Does not auto-promote or change policy. Financials are econ-sim-v3, not P&L.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from olist_ml.outcomes.impact import (  # noqa: E402
    render_impact_markdown,
    summarize_from_replay_policy,
    summarize_simulated_impact,
)
from olist_ml.outcomes.ledger import DecisionLedger  # noqa: E402

dag = None  # type: ignore[assignment]

DEFAULT_LEDGER = Path("artifacts/decision_ledger.jsonl")
DEFAULT_OUT = Path("artifacts/decision_eval_report.json")
DEFAULT_MD = Path("artifacts/decision_impact.md")
DEFAULT_REPLAY = Path("artifacts/policy_replay_report.json")


def run_decision_evaluation(
    ledger_path: Path = DEFAULT_LEDGER,
    output_path: Path = DEFAULT_OUT,
    markdown_path: Path = DEFAULT_MD,
    replay_path: Path = DEFAULT_REPLAY,
) -> dict[str, Any]:
    ledger = DecisionLedger(ledger_path)
    rows = ledger.read_all()
    impact = summarize_simulated_impact(rows)
    if impact["n_actions"] == 0 and replay_path.exists():
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        noc = (replay.get("policies") or {}).get("noc")
        if noc:
            impact = summarize_from_replay_policy(
                noc,
                n_orders=int(replay.get("n_orders") or 0),
                policy_name="noc",
            )
    by_type: dict[str, int] = {}
    for row in rows:
        key = str(row.get("record_type") or "unknown")
        by_type[key] = by_type.get(key, 0) + 1

    used_replay = str(impact.get("source") or "").startswith("policy_replay")
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "ledger_path": str(ledger_path),
        "replay_path": str(replay_path) if used_replay else None,
        "record_counts": by_type,
        **impact,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(render_impact_markdown(report), encoding="utf-8")
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
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    parser.add_argument("--replay", type=Path, default=DEFAULT_REPLAY)
    args = parser.parse_args()
    report = run_decision_evaluation(
        args.ledger, args.output, args.markdown, args.replay
    )
    print(report["headline"])
    print()
    print(report["narrative"])
    print()
    print(report["disclaimer"])
    print()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
