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


def test_prediction_service_hydrates_omitted_seller_features(monkeypatch) -> None:
    from olist_ml.config import Settings
    from olist_ml.inference.predictor import PredictionService
    from olist_ml.schemas import PredictRequest

    now = datetime.now(tz=UTC)
    frame = pd.DataFrame(
        [
            {
                "seller_id": "s_online",
                "feature_timestamp": now,
                "event_timestamp": now,
                **{c: 9.0 for c in ONLINE_SELLER_FEATURES},
            }
        ]
    )
    settings = Settings(feast_online_enabled=False)
    service = PredictionService(settings)
    client = FeastSellerClient(freshness_sla_hours=36)
    monkeypatch.setattr(client, "_get_store", lambda: _FakeStore(frame))
    # Serving freshness is vs wall clock; inject the client after construction so
    # hydrate runs even when feast_online_enabled is off (Cloud Run default).
    service.feast_client = client
    req = PredictRequest(
        order_id="o",
        seller_id="s_online",
        purchase_timestamp=now,
        item_count=1,
        basket_value=10.0,
        freight_value=1.0,
        estimated_delivery_horizon_days=5.0,
    )
    filled, stale = service.hydrate_request(req)
    assert stale is False
    assert filled.seller_order_count_30d == 9.0
    assert filled.seller_late_rate_90d == 9.0
    # Explicit request values win over Feast.
    req2 = req.model_copy(update={"seller_order_count_30d": 3.0})
    filled2, _ = service.hydrate_request(req2)
    assert filled2.seller_order_count_30d == 3.0
    assert filled2.seller_late_rate_30d == 9.0
