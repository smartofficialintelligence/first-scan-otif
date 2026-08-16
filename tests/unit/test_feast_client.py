"""Unit tests for Feast seller client freshness / defaults (no GCP required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pandas as pd

from olist_ml.features.contracts import ONLINE_SELLER_FEATURES
from olist_ml.features.feast_client import FeastSellerClient


class _FakeStore:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def get_feature_service(self, name: str):  # noqa: ANN201
        return name

    def get_online_features(self, features, entity_rows):  # noqa: ANN001, ANN201
        return SimpleNamespace(to_df=lambda: self._frame)


def test_feast_client_marks_stale_and_maps_features(monkeypatch) -> None:
    now = datetime(2020, 1, 10, tzinfo=UTC)
    fresh_ts = now - timedelta(hours=1)
    stale_ts = now - timedelta(hours=48)
    frame = pd.DataFrame(
        [
            {
                "seller_id": "s_fresh",
                "feature_timestamp": fresh_ts,
                "event_timestamp": fresh_ts,
                **{c: 1.0 for c in ONLINE_SELLER_FEATURES},
            },
            {
                "seller_id": "s_stale",
                "feature_timestamp": stale_ts,
                "event_timestamp": stale_ts,
                **{c: 2.0 for c in ONLINE_SELLER_FEATURES},
            },
            {
                "seller_id": "s_missing",
                "feature_timestamp": None,
                "event_timestamp": None,
                **{c: None for c in ONLINE_SELLER_FEATURES},
            },
        ]
    )
    client = FeastSellerClient(freshness_sla_hours=36)
    monkeypatch.setattr(client, "_get_store", lambda: _FakeStore(frame))
    rows = {r.seller_id: r for r in client.get_online_features(["s_fresh", "s_stale", "s_missing"], now=now)}
    assert rows["s_fresh"].stale is False
    assert rows["s_stale"].stale is True
    assert rows["s_missing"].stale is True
    assert rows["s_fresh"].features["seller_order_count_30d"] == 1.0
    assert rows["s_missing"].features["seller_late_rate_30d"] == 0.0
