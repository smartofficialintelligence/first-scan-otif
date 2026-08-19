#!/usr/bin/env python3
"""Run offline policy replay on a scored CSV/parquet holdout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from olist_ml.decisions.replay import replay_from_frame
from olist_ml.outcomes.ledger import DecisionLedger


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare NO_ACTION / threshold / NOC policies")
    parser.add_argument(
        "--input", type=Path, required=True, help="CSV/parquet with scores + labels"
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/policy_replay_report.json"))
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="If set, append NOC simulated actions to this JSONL ledger",
    )
    parser.add_argument("--probability-col", default="promise_miss_probability")
    parser.add_argument("--label-col", default="promise_miss")
    parser.add_argument("--basket-col", default="basket_value")
    parser.add_argument("--threshold", type=float, default=0.70)
    parser.add_argument("--config", type=Path, default=Path("config/policy_economics.yaml"))
    args = parser.parse_args(argv)

    if args.input.suffix == ".parquet":
        frame = pd.read_parquet(args.input)
    else:
        frame = pd.read_csv(args.input)

    report = replay_from_frame(
        frame,
        probability_col=args.probability_col,
        label_col=args.label_col,
        basket_col=args.basket_col,
        threshold=args.threshold,
        config_path=str(args.config),
        ledger=DecisionLedger(args.ledger) if args.ledger else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(report["business_sim"]["headline"])
    print(report["business_sim"]["disclaimer"])
    print(json.dumps(report["policies"], indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
