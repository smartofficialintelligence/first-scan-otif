"""Local Feast materialize must write one current-state row per seller."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from olist_ml.data.loaders import load_olist_tables
from olist_ml.data.targets import build_labeled_orders
from olist_ml.features.build import build_feature_table
from olist_ml.features.contracts import ONLINE_SELLER_FEATURES

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data" / "fixtures"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "feast_materialize_local", ROOT / "scripts/feast_materialize_local.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_online_rows_are_latest_scan_per_seller_not_first() -> None:
    """An online store holds current seller state. First-scan rows would be stale history."""
    materialize = _load_module()
    rows = materialize.build_seller_rows(FIXTURES)

    tables = load_olist_tables(FIXTURES)
    labeled = build_labeled_orders(tables["orders"])
    features = build_feature_table(tables, labeled).dropna(subset=["seller_id", "handoff_ts"])
    features["handoff_ts"] = pd.to_datetime(features["handoff_ts"], utc=True)

    assert rows["seller_id"].is_unique
    assert set(ONLINE_SELLER_FEATURES).issubset(rows.columns)
    assert "event_timestamp" in rows.columns
    assert (rows["feature_timestamp"] == rows["event_timestamp"]).all()

    latest = features.sort_values("handoff_ts").groupby("seller_id", as_index=False).tail(1)
    merged = rows.merge(
        latest[["seller_id", "handoff_ts", "seller_late_rate_30d"]],
        on="seller_id",
        suffixes=("_online", "_latest"),
    )
    assert len(merged) == len(rows)
    assert (merged["event_timestamp"] == merged["handoff_ts"]).all()
    assert (merged["seller_late_rate_30d_online"] == merged["seller_late_rate_30d_latest"]).all()

    earliest = features.sort_values("handoff_ts").groupby("seller_id", as_index=False).head(1)
    multi = features.groupby("seller_id").size()
    multi_sellers = list(multi[multi > 1].index)
    assert multi_sellers, "fixtures must include a seller with more than one order"
    first_ts = earliest.set_index("seller_id")["handoff_ts"]
    online_ts = rows.set_index("seller_id")["event_timestamp"]
    assert any(online_ts.loc[sid] != first_ts.loc[sid] for sid in multi_sellers)
