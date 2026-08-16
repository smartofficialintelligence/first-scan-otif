#!/usr/bin/env python3
"""Offline vs online seller feature parity check (Milestone 3 accept).

Compares Feast online values to the latest BigQuery row per seller within tolerance.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

from olist_ml.features.contracts import ONLINE_SELLER_FEATURES
from olist_ml.features.feast_client import FeastSellerClient
from olist_ml.logging import get_logger, setup_logging

logger = get_logger(__name__)


def _latest_bq(project: str, seller_ids: list[str]) -> pd.DataFrame:
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    # Parameterize via UNNEST
    sql = f"""
    with ranked as (
      select
        seller_id,
        event_timestamp,
        seller_order_count_7d,
        seller_order_count_30d,
        seller_order_count_90d,
        seller_late_rate_7d,
        seller_late_rate_30d,
        seller_late_rate_90d,
        row_number() over (partition by seller_id order by event_timestamp desc) as rn
      from `{project}.ml.fct_seller_features`
      where seller_id in unnest(@seller_ids)
    )
    select * except(rn) from ranked where rn = 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("seller_ids", "STRING", seller_ids),
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe()


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("feature_repo"))
    parser.add_argument("--tol", type=float, default=1e-6)
    parser.add_argument("--limit-sellers", type=int, default=20)
    args = parser.parse_args()

    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project:
        raise SystemExit("GCP_PROJECT_ID is required")

    from google.cloud import bigquery

    sellers = (
        bigquery.Client(project=project)
        .query(
            f"""
            select distinct seller_id
            from `{project}.ml.fct_seller_features`
            order by seller_id
            limit {int(args.limit_sellers)}
            """
        )
        .to_dataframe()["seller_id"]
        .astype(str)
        .tolist()
    )
    if not sellers:
        logger.error("No sellers found in ml.fct_seller_features")
        return 1

    client = FeastSellerClient(repo_path=args.repo)
    online_rows = client.get_online_features(sellers)
    online = {r.seller_id: r for r in online_rows}
    offline = _latest_bq(project, sellers).set_index("seller_id")

    mismatches = 0
    for sid in sellers:
        if sid not in online:
            logger.error("Missing online row for %s", sid)
            mismatches += 1
            continue
        if sid not in offline.index:
            logger.error("Missing offline row for %s", sid)
            mismatches += 1
            continue
        on = online[sid]
        off = offline.loc[sid]
        for col in ONLINE_SELLER_FEATURES:
            a = float(on.features.get(col, 0.0))
            b = float(off[col]) if pd.notna(off[col]) else 0.0
            if abs(a - b) > args.tol:
                logger.error("Mismatch %s.%s online=%s offline=%s", sid, col, a, b)
                mismatches += 1
        logger.info(
            "seller=%s stale=%s ts=%s ok_features=%s",
            sid,
            on.stale,
            on.feature_timestamp,
            mismatches == 0,
        )

    if mismatches:
        logger.error("Parity FAILED with %s mismatches", mismatches)
        return 1
    logger.info("Parity OK for %s sellers (tol=%s)", len(sellers), args.tol)
    return 0


if __name__ == "__main__":
    sys.exit(main())
