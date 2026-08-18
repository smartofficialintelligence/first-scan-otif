#!/usr/bin/env python3
"""Evaluate delayed-label quality on released rows only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from olist_ml.monitoring.delayed_eval import run_evaluate_delayed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Delayed-label PR-AUC / Brier (released only)")
    parser.add_argument("--log-path", type=Path, default=Path("artifacts/prediction_logs.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/delayed_eval.json"))
    parser.add_argument(
        "--baseline-pr-auc",
        type=float,
        default=None,
        help="Rolling baseline PR-AUC; drop > 0.03 sets quality_alarm",
    )
    parser.add_argument(
        "--champion-pr-auc",
        type=float,
        default=None,
        help="Offline champion PR-AUC; canary floor is champion − 0.02",
    )
    args = parser.parse_args(argv)
    report = run_evaluate_delayed(
        log_path=args.log_path,
        out_path=args.out,
        baseline_pr_auc=args.baseline_pr_auc,
        champion_pr_auc=args.champion_pr_auc,
    )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
