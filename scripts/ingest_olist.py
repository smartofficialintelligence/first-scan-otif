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

import pandas as pd
from google.cloud import bigquery

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


def _read_csv(path: Path, key: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Align dtypes lightly for timestamp columns declared in schema.
    for field in SCHEMAS[key]:
        if field.field_type == "TIMESTAMP" and field.name in df.columns:
            df[field.name] = pd.to_datetime(df[field.name], utc=True, errors="coerce")
    return df


def load_to_bq(data_dir: Path, project_id: str, dataset: str = "olist_raw") -> None:
    client = bigquery.Client(project=project_id)
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset}")
    dataset_ref.location = "US"
    client.create_dataset(dataset_ref, exists_ok=True)

    for key, filename in REQUIRED_FILES.items():
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        table_id = f"{project_id}.{dataset}.{TABLE_MAP[key]}"
        df = _read_csv(path, key)
        job_config = bigquery.LoadJobConfig(
            schema=SCHEMAS[key],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        logger.info("Loading %s (%s rows) -> %s", path, len(df), table_id)
        job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
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
    args.project_id = str(args.project_id).strip()
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise SystemExit("GOOGLE_APPLICATION_CREDENTIALS must point to an SA JSON file")
    load_to_bq(args.data_dir, args.project_id, args.dataset)


if __name__ == "__main__":
    main()
