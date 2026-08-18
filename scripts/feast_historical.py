#!/usr/bin/env python3
"""Offline historical retrieval via Feast (training path).

Builds an entity dataframe from ml.fct_order_features and calls
get_historical_features for seller_online_v1.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

from olist_ml.logging import get_logger, setup_logging

logger = get_logger(__name__)


def _load_entity_df(project: str, limit: int | None) -> pd.DataFrame:
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    sql = f"""
    select
      seller_id,
      handoff_ts as event_timestamp
    from `{project}.ml.fct_order_features`
    where seller_id is not null
      and handoff_ts is not null
    order by handoff_ts
    """
    if limit:
        sql += f"\nlimit {int(limit)}"
    return client.query(sql).to_dataframe()


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("feature_repo"))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("artifacts/feast_historical.parquet"))
    args = parser.parse_args()

    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project:
        raise SystemExit("GCP_PROJECT_ID is required")

    from feast import FeatureStore

    entity_df = _load_entity_df(project, args.limit)
    logger.info("Entity rows: %s", len(entity_df))
    store = FeatureStore(repo_path=str(args.repo))
    job = store.get_historical_features(
        entity_df=entity_df,
        features=store.get_feature_service("seller_online_v1"),
    )
    out = job.to_df()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    logger.info("Wrote %s rows -> %s", len(out), args.out)
    print(out.head().to_string(index=False))


if __name__ == "__main__":
    main()
