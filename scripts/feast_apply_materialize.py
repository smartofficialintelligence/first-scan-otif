#!/usr/bin/env python3
"""Apply Feast registry and materialize seller online features from BigQuery.

Requires:
  GCP_PROJECT_ID
  GOOGLE_APPLICATION_CREDENTIALS
  dbt mart ml.fct_seller_features (run dbt build first)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from olist_ml.logging import get_logger, setup_logging

logger = get_logger(__name__)


def _apply_cli(repo: Path) -> None:
    feast_bin = Path(sys.executable).with_name("feast")
    cmd = [str(feast_bin) if feast_bin.exists() else "feast", "-c", str(repo), "apply"]
    subprocess.run(cmd, check=True)


def pd_to_utc(ts: object) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    import pandas as pd

    out = pd.Timestamp(ts).to_pydatetime()
    return out if out.tzinfo else out.replace(tzinfo=UTC)


def _source_time_range(project: str) -> tuple[datetime, datetime]:
    """Use actual mart timestamps so fixture-era rows are materialized."""
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    row = list(
        client.query(
            f"""
            select
              min(event_timestamp) as min_ts,
              max(event_timestamp) as max_ts
            from `{project}.ml.fct_seller_features`
            """
        ).result()
    )[0]
    if row.min_ts is None or row.max_ts is None:
        raise SystemExit(f"No rows in {project}.ml.fct_seller_features — run dbt build first")
    start = pd_to_utc(row.min_ts) - timedelta(days=1)
    end = pd_to_utc(row.max_ts) + timedelta(days=1)
    # Keep end at least now so materialize window is valid for online serving demos.
    now = datetime.now(tz=UTC)
    if end < now:
        end = now
    return start, end


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("feature_repo"))
    parser.add_argument(
        "--days",
        type=int,
        default=0,
        help="If >0, ignore source min/max and materialize now-days..now",
    )
    parser.add_argument("--skip-materialize", action="store_true")
    args = parser.parse_args()

    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project:
        raise SystemExit("GCP_PROJECT_ID is required")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS is required")

    from feast import FeatureStore

    logger.info("feast apply in %s (project=%s)", args.repo, project)
    _apply_cli(args.repo)

    if args.skip_materialize:
        logger.info("Skipping materialize")
        return

    store = FeatureStore(repo_path=str(args.repo))
    if args.days > 0:
        end = datetime.now(tz=UTC)
        start = end - timedelta(days=args.days)
    else:
        start, end = _source_time_range(project)
    logger.info("Materializing seller_liveness_v1 from %s to %s", start, end)
    store.materialize(start_date=start, end_date=end)
    logger.info("Materialize complete")


if __name__ == "__main__":
    main()
