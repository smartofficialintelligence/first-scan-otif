#!/usr/bin/env python3
"""Write artifacts/monitoring_dashboard.json (M8 exported metrics)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from olist_ml.monitoring.export import DEFAULT_OUT, export_monitoring_snapshot


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    snap = export_monitoring_snapshot(out_path=args.out)
    print(json.dumps(snap, indent=2, default=str))


if __name__ == "__main__":
    main()
