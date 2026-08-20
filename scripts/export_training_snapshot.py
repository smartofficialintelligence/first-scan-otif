#!/usr/bin/env python3
"""Export the dbt training mart to a parquet the trainer actually reads.

``ml.fct_training_snapshot`` used to be a mart nothing consumed. This lands it
at ``artifacts/fct_training_snapshot.parquet``, which
``olist_ml.features.historical.apply_warehouse_features`` picks up on the next
train — so the warehouse becomes an input to the champion rather than a
parallel export.

The snapshot is used only when it carries every contract column; otherwise the
trainer logs why and falls back to the pandas builder.

Requires:
  GCP_PROJECT_ID
  GOOGLE_APPLICATION_CREDENTIALS (path to SA JSON)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from olist_ml.features.contracts import FEATURE_COLUMNS, TARGET_COLUMN
from olist_ml.features.historical import SNAPSHOT_FILENAME
from olist_ml.logging import get_logger, setup_logging

logger = get_logger(__name__)


def export_snapshot(
    project_id: str,
    out: Path,
    *,
    dataset: str = "ml",
    table: str = "fct_training_snapshot",
    limit: int | None = None,
) -> Path:
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    sql = f"select * from `{project_id}.{dataset}.{table}`"
    if limit:
        sql += f" limit {int(limit)}"
    logger.info("Reading %s.%s.%s", project_id, dataset, table)
    frame = client.query(sql).to_dataframe()

    missing = {"handoff_ts", TARGET_COLUMN, *FEATURE_COLUMNS} - set(frame.columns)
    if missing:
        # Export anyway so the gap is inspectable, but say so plainly — the
        # trainer will refuse this file and use the pandas builder.
        logger.warning(
            "Snapshot is missing %d contract columns and will NOT be used for "
            "training: %s",
            len(missing),
            sorted(missing)[:10],
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)
    logger.info("Wrote %s rows -> %s", len(frame), out)
    return out


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", default=os.environ.get("GCP_PROJECT_ID"))
    parser.add_argument("--dataset", default="ml")
    parser.add_argument("--table", default="fct_training_snapshot")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("artifacts") / SNAPSHOT_FILENAME)
    args = parser.parse_args()

    if not args.project_id:
        raise SystemExit("GCP_PROJECT_ID is required")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS must point to an SA JSON file")

    export_snapshot(
        str(args.project_id).strip(),
        args.out,
        dataset=args.dataset,
        table=args.table,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
