#!/usr/bin/env python3
"""Populate the Feast SQLite online store from local CSVs — no cloud, no cost.

The source of record for seller features is the dbt mart ``ml.fct_seller_features``
in BigQuery; ``make feast-apply`` materializes from it and needs credentials.
This script is the **$0 equivalent for the local and demo path**: it derives the
same six ``ONLINE_SELLER_FEATURES`` from the same point-in-time pandas builder
that trains the champion, then writes them into the same Feast online store
through the same Feast API.

What is identical either way: the entity, the feature view, the feature service,
the online store, and the serving code path. What differs: where the rows came
from (local pandas vs the warehouse). Say that out loud — it is a cost trade-off,
not a claim that BigQuery ran.

Each seller gets one row: their history as of their most recent carrier scan,
which is what an online store holds — current state, not per-order history.
Registry and online store are built with an online-only config, so this needs
only the light ``feast`` package (the BigQuery offline driver lives in the
``gcp`` extra).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.build import build_feature_table
from olist_ml.features.contracts import ONLINE_SELLER_FEATURES
from olist_ml.logging import get_logger, setup_logging

logger = get_logger(__name__)

REPO_DIR = Path("feature_repo")
DEFAULT_STORE_DIR = Path("data/feast")


def build_seller_rows(data_dir: Path) -> pd.DataFrame:
    """One row per seller: their PIT history as of their latest carrier scan."""
    tables = load_olist_tables(data_dir)
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled)

    missing = [c for c in ONLINE_SELLER_FEATURES if c not in features.columns]
    if missing:
        raise SystemExit(f"Feature table is missing online columns: {missing}")

    frame = features.dropna(subset=["seller_id", "handoff_ts"]).copy()
    frame["handoff_ts"] = pd.to_datetime(frame["handoff_ts"], utc=True)
    latest = frame.sort_values("handoff_ts").groupby("seller_id", as_index=False).tail(1)

    rows = latest[["seller_id", "handoff_ts", *ONLINE_SELLER_FEATURES]].copy()
    rows["seller_id"] = rows["seller_id"].astype(str)
    for col in ONLINE_SELLER_FEATURES:
        rows[col] = rows[col].astype(float)
    # event_timestamp drives Feast TTL; feature_timestamp is the freshness value
    # the serving client reads back to decide staleness.
    rows = rows.rename(columns={"handoff_ts": "event_timestamp"})
    rows["feature_timestamp"] = rows["event_timestamp"]
    rows["created"] = pd.Timestamp.now(tz="UTC")
    return rows


def _load_definitions() -> tuple[object, object, object]:
    """Import the real feature_repo definitions (not a copy of them)."""
    repo = REPO_DIR.resolve()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from entities import seller  # type: ignore[import-not-found]
    from features import seller_liveness_v1, seller_online_v1  # type: ignore[import-not-found]

    return seller, seller_liveness_v1, seller_online_v1


def materialize_local(data_dir: Path, store_dir: Path, *, freshen: bool = False) -> int:
    from feast import FeatureStore, RepoConfig
    from feast.infra.online_stores.sqlite import SqliteOnlineStoreConfig

    store_dir.mkdir(parents=True, exist_ok=True)
    rows = build_seller_rows(data_dir)

    if freshen:
        # Olist data ends in 2018, so real event timestamps are always stale
        # against a 36h SLA. For a live demo, shift them to now and say so.
        now = pd.Timestamp.now(tz="UTC")
        rows["event_timestamp"] = now
        rows["feature_timestamp"] = now
        logger.warning(
            "--freshen: timestamps rewritten to now so lookups read fresh. "
            "Feature VALUES are still the historical point-in-time ones."
        )

    seller, feature_view, feature_service = _load_definitions()
    config = RepoConfig(
        project="olist_ml",
        provider="local",
        registry={"registry_type": "file", "path": str(store_dir / "registry.db")},
        online_store=SqliteOnlineStoreConfig(path=str(store_dir / "online.db")),
        entity_key_serialization_version=3,
    )
    store = FeatureStore(config=config)
    store.apply([seller, feature_view, feature_service])
    store.write_to_online_store(feature_view.name, rows)
    logger.info("Wrote %d seller rows -> %s", len(rows), store_dir / "online.db")
    return len(rows)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/fixtures"))
    parser.add_argument("--store-dir", type=Path, default=DEFAULT_STORE_DIR)
    parser.add_argument(
        "--freshen",
        action="store_true",
        help="Rewrite timestamps to now so 2018 data reads fresh in a demo",
    )
    args = parser.parse_args()
    count = materialize_local(args.data_dir, args.store_dir, freshen=args.freshen)
    print(f"Materialized {count} sellers into {args.store_dir}/online.db")


if __name__ == "__main__":
    main()
