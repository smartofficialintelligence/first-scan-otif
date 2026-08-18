#!/usr/bin/env python3
"""Write the H5 retrain-approval flag. Alarms do not imply approval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from olist_ml.monitoring.h5 import DEFAULT_H5_PATH, write_h5_approval


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Approve (or revoke) H5 retrain")
    parser.add_argument("--approved-by", type=str, default="portfolio-maintainer")
    parser.add_argument("--reason", type=str, default="drift", choices=["drift", "monthly", "manual"])
    parser.add_argument("--revoke", action="store_true")
    parser.add_argument("--path", type=Path, default=DEFAULT_H5_PATH)
    args = parser.parse_args(argv)
    body = write_h5_approval(
        approved=not args.revoke,
        approved_by=args.approved_by,
        reason=args.reason,
        path=args.path,
    )
    print(json.dumps(body, indent=2))


if __name__ == "__main__":
    main()
