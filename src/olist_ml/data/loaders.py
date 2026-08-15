"""Load local Olist CSV tables."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from olist_ml.logging import get_logger

logger = get_logger(__name__)

REQUIRED_FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing Olist file: {path}")
    return pd.read_csv(path)


def load_olist_tables(data_dir: Path | str) -> dict[str, pd.DataFrame]:
    """Load required Olist CSVs from a directory."""
    root = Path(data_dir)
    tables: dict[str, pd.DataFrame] = {}
    for key, filename in REQUIRED_FILES.items():
        path = root / filename
        logger.info("Loading %s", path)
        tables[key] = _read_csv(path)
    return tables


def table_summary(tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    return {name: {"rows": len(df), "cols": list(df.columns)} for name, df in tables.items()}
