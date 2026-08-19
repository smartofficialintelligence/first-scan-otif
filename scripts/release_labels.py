#!/usr/bin/env python3
"""Mark delayed labels released where virtual_now >= label_release_at."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from olist_ml.monitoring.labels import run_release_labels


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Release delayed labels on prediction logs")
    parser.add_argument("--log-path", type=Path, default=Path("artifacts/prediction_logs.jsonl"))
    parser.add_argument(
        "--virtual-now",
        type=str,
        required=True,
        help="ISO-8601 demo clock (e.g. 2018-09-01T00:00:00Z)",
    )
    parser.add_argument("--out", type=Path, default=None, help="Defaults to --log-path (in place)")
    args = parser.parse_args(argv)
    virtual_now = datetime.fromisoformat(args.virtual_now.replace("Z", "+00:00"))
    if virtual_now.tzinfo is None:
        virtual_now = virtual_now.replace(tzinfo=UTC)
    result = run_release_labels(
        log_path=args.log_path,
        virtual_now=virtual_now,
        out_path=args.out,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
