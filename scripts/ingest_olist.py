#!/usr/bin/env python3
"""Load Olist CSVs into BigQuery raw dataset.

Requires:
  GCP_PROJECT_ID
  GOOGLE_APPLICATION_CREDENTIALS (path to SA JSON)
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from olist_ml.data.loaders import REQUIRED_FILES
from olist_ml.logging import get_logger, setup_logging

logger = get_logger(__name__)

TABLE_MAP = {
    "orders": "orders",
    "order_items": "order_items",
    "customers": "customers",
    "products": "products",
    "sellers": "sellers",
    "payments": "payments",
    "geolocation": "geolocation",
    "category_translation": "category_translation",
}


def load_to_bq(data_dir: Path, project_id: str, dataset: str = "olist_raw") -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset}")
    dataset_ref.location = "US"
    client.create_dataset(dataset_ref, exists_ok=True)

    for key, filename in REQUIRED_FILES.items():
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        table_id = f"{project_id}.{dataset}.{TABLE_MAP[key]}"
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            autodetect=True,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        logger.info("Loading %s -> %s", path, table_id)
        with path.open("rb") as fh:
            job = client.load_table_from_file(fh, table_id, job_config=job_config)
        job.result()
        table = client.get_table(table_id)
        logger.info("Loaded %s rows into %s", table.num_rows, table_id)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--project-id", default=os.environ.get("GCP_PROJECT_ID"))
    parser.add_argument("--dataset", default="olist_raw")
    args = parser.parse_args()
    if not args.project_id:
        raise SystemExit("GCP_PROJECT_ID is required")
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS must point to an SA JSON file")
    load_to_bq(args.data_dir, args.project_id, args.dataset)


if __name__ == "__main__":
    main()
