#!/usr/bin/env python3
"""Land Olist CSVs in the raw GCS bucket, then load BigQuery from those objects.

CSV -> gs://{bucket}/olist/<file> -> BigQuery `olist_raw`. Staging through
Cloud Storage is why the bucket Terraform creates exists: it is the raw landing
zone and the load's source of record, so a BigQuery table can always be rebuilt
from the object that produced it.

Requires:
  GCP_PROJECT_ID
  GOOGLE_APPLICATION_CREDENTIALS (path to SA JSON)
Optional:
  GCS_RAW_BUCKET (defaults to the Terraform name: {prefix}-raw-{project})
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from google.cloud import bigquery, storage

from olist_ml.data.loaders import REQUIRED_FILES
from olist_ml.logging import get_logger, setup_logging

logger = get_logger(__name__)

DEFAULT_BUCKET_PREFIX = "olist-ml"
GCS_RAW_PREFIX = "olist"

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

# Explicit schemas so small all-string CSVs (e.g. category_translation) keep
# header names instead of BigQuery autodetect inventing string_field_N.
SCHEMAS: dict[str, list[bigquery.SchemaField]] = {
    "orders": [
        bigquery.SchemaField("order_id", "STRING"),
        bigquery.SchemaField("customer_id", "STRING"),
        bigquery.SchemaField("order_status", "STRING"),
        bigquery.SchemaField("order_purchase_timestamp", "TIMESTAMP"),
        bigquery.SchemaField("order_approved_at", "TIMESTAMP"),
        bigquery.SchemaField("order_delivered_carrier_date", "TIMESTAMP"),
        bigquery.SchemaField("order_delivered_customer_date", "TIMESTAMP"),
        bigquery.SchemaField("order_estimated_delivery_date", "TIMESTAMP"),
    ],
    "order_items": [
        bigquery.SchemaField("order_id", "STRING"),
        bigquery.SchemaField("order_item_id", "INTEGER"),
        bigquery.SchemaField("product_id", "STRING"),
        bigquery.SchemaField("seller_id", "STRING"),
        bigquery.SchemaField("shipping_limit_date", "TIMESTAMP"),
        bigquery.SchemaField("price", "FLOAT"),
        bigquery.SchemaField("freight_value", "FLOAT"),
    ],
    "customers": [
        bigquery.SchemaField("customer_id", "STRING"),
        bigquery.SchemaField("customer_unique_id", "STRING"),
        bigquery.SchemaField("customer_zip_code_prefix", "INTEGER"),
        bigquery.SchemaField("customer_city", "STRING"),
        bigquery.SchemaField("customer_state", "STRING"),
    ],
    "products": [
        bigquery.SchemaField("product_id", "STRING"),
        bigquery.SchemaField("product_category_name", "STRING"),
        bigquery.SchemaField("product_name_lenght", "INTEGER"),
        bigquery.SchemaField("product_description_lenght", "INTEGER"),
        bigquery.SchemaField("product_photos_qty", "INTEGER"),
        bigquery.SchemaField("product_weight_g", "FLOAT"),
        bigquery.SchemaField("product_length_cm", "FLOAT"),
        bigquery.SchemaField("product_height_cm", "FLOAT"),
        bigquery.SchemaField("product_width_cm", "FLOAT"),
    ],
    "sellers": [
        bigquery.SchemaField("seller_id", "STRING"),
        bigquery.SchemaField("seller_zip_code_prefix", "INTEGER"),
        bigquery.SchemaField("seller_city", "STRING"),
        bigquery.SchemaField("seller_state", "STRING"),
    ],
    "payments": [
        bigquery.SchemaField("order_id", "STRING"),
        bigquery.SchemaField("payment_sequential", "INTEGER"),
        bigquery.SchemaField("payment_type", "STRING"),
        bigquery.SchemaField("payment_installments", "INTEGER"),
        bigquery.SchemaField("payment_value", "FLOAT"),
    ],
    "geolocation": [
        bigquery.SchemaField("geolocation_zip_code_prefix", "INTEGER"),
        bigquery.SchemaField("geolocation_lat", "FLOAT"),
        bigquery.SchemaField("geolocation_lng", "FLOAT"),
        bigquery.SchemaField("geolocation_city", "STRING"),
        bigquery.SchemaField("geolocation_state", "STRING"),
    ],
    "category_translation": [
        bigquery.SchemaField("product_category_name", "STRING"),
        bigquery.SchemaField("product_category_name_english", "STRING"),
    ],
}


def raw_bucket_name(project_id: str) -> str:
    """Terraform names the bucket ``{name_prefix}-raw-{project_id}``."""
    override = os.environ.get("GCS_RAW_BUCKET", "").strip()
    if override:
        return override
    return f"{DEFAULT_BUCKET_PREFIX}-raw-{project_id}"


def upload_raw_to_gcs(
    data_dir: Path,
    project_id: str,
    bucket_name: str,
    *,
    prefix: str = GCS_RAW_PREFIX,
) -> dict[str, str]:
    """Upload each required CSV and return {table key: gs:// URI}."""
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    uris: dict[str, str] = {}
    for key, filename in REQUIRED_FILES.items():
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        blob_name = f"{prefix}/{filename}"
        bucket.blob(blob_name).upload_from_filename(str(path), content_type="text/csv")
        uris[key] = f"gs://{bucket_name}/{blob_name}"
        logger.info("Uploaded %s -> %s", path, uris[key])
    return uris


def load_to_bq(
    uris: dict[str, str],
    project_id: str,
    dataset: str = "olist_raw",
) -> None:
    """Load BigQuery from the GCS objects just written (explicit schemas)."""
    client = bigquery.Client(project=project_id)
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset}")
    dataset_ref.location = "US"
    client.create_dataset(dataset_ref, exists_ok=True)

    for key, uri in uris.items():
        table_id = f"{project_id}.{dataset}.{TABLE_MAP[key]}"
        job_config = bigquery.LoadJobConfig(
            schema=SCHEMAS[key],
            source_format=bigquery.SourceFormat.CSV,
            # Explicit schema (not autodetect) keeps header names and casts the
            # timestamp columns; row 1 is the header.
            skip_leading_rows=1,
            allow_quoted_newlines=True,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        logger.info("Loading %s -> %s", uri, table_id)
        client.load_table_from_uri(uri, table_id, job_config=job_config).result()
        table = client.get_table(table_id)
        logger.info("Loaded %s rows into %s", table.num_rows, table_id)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--project-id", default=os.environ.get("GCP_PROJECT_ID"))
    parser.add_argument("--dataset", default="olist_raw")
    parser.add_argument(
        "--bucket",
        default=None,
        help="Raw GCS bucket (default: $GCS_RAW_BUCKET or the Terraform name)",
    )
    args = parser.parse_args()
    if not args.project_id:
        raise SystemExit("GCP_PROJECT_ID is required")
    args.project_id = str(args.project_id).strip()
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS must point to an SA JSON file")
    bucket = args.bucket or raw_bucket_name(args.project_id)
    uris = upload_raw_to_gcs(args.data_dir, args.project_id, bucket)
    load_to_bq(uris, args.project_id, args.dataset)


if __name__ == "__main__":
    main()
