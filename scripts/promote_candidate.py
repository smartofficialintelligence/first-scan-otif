#!/usr/bin/env python3
"""Promote a trained candidate to champion (H6 — explicit human decision).

Training never writes the champion path; this script is the only promote path.
"""

from __future__ import annotations

import argparse
import json

from olist_ml.config import get_settings
from olist_ml.logging import setup_logging
from olist_ml.training.promote import latest_candidate_version, promote_candidate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=None,
        help="Candidate model_version under artifacts/candidates/ (default: latest)",
    )
    parser.add_argument(
        "--approved-by",
        required=True,
        help="Name of the person approving the champion swap (H6)",
    )
    parser.add_argument("--note", default="", help="Optional context for the promote record")
    args = parser.parse_args(argv)

    setup_logging()
    settings = get_settings()
    version = args.version or latest_candidate_version(settings)
    if version is None:
        raise SystemExit("No candidates found — run training first (make train-pipeline)")
    record = promote_candidate(
        settings,
        version,
        approved_by=args.approved_by,
        note=args.note,
    )
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
