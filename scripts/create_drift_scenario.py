#!/usr/bin/env python3
"""Apply a named drift scenario to a holdout CSV (docs/simulation.md)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from olist_ml.monitoring.scenarios import apply_drift_scenario


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Mutate holdout features for a drift scenario")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--scenario",
        type=str,
        required=True,
        choices=["baseline", "drift_seller_late", "drift_geo", "bad_canary"],
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fraction", type=float, default=0.30)
    args = parser.parse_args(argv)
    frame = pd.read_csv(args.input)
    out = apply_drift_scenario(frame, args.scenario, seed=args.seed, fraction=args.fraction)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"Wrote {len(out)} rows → {args.output} scenario={args.scenario}")


if __name__ == "__main__":
    main()
