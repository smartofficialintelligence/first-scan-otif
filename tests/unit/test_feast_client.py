"""Unit tests for Feast seller client freshness / defaults (no GCP required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

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


def test_epoch_seconds_timestamp_drives_freshness(monkeypatch) -> None:
    """Feast UnixTimestamp values may arrive as epoch seconds, not datetimes."""
    now = datetime(2020, 1, 10, tzinfo=UTC)
    fresh_epoch = (now - timedelta(hours=1)).timestamp()
    stale_epoch = (now - timedelta(hours=48)).timestamp()
    frame = pd.DataFrame(
        [
            {
                "seller_id": "s_fresh",
                "feature_timestamp": fresh_epoch,
                **{c: 1.0 for c in ONLINE_SELLER_FEATURES},
            },
            {
                "seller_id": "s_stale",
                "feature_timestamp": stale_epoch,
                **{c: 1.0 for c in ONLINE_SELLER_FEATURES},
            },
        ]
    )
    client = FeastSellerClient(freshness_sla_hours=36)
    monkeypatch.setattr(client, "_get_store", lambda: _FakeStore(frame))
    rows = {r.seller_id: r for r in client.get_online_features(["s_fresh", "s_stale"], now=now)}
    assert rows["s_fresh"].stale is False
    assert rows["s_stale"].stale is True


def test_naive_feature_timestamp_is_treated_as_utc(monkeypatch) -> None:
    now = datetime(2020, 1, 10, tzinfo=UTC)
    naive = datetime(2020, 1, 10, 0, 0, 0)  # no tzinfo
    frame = pd.DataFrame(
        [
            {
                "seller_id": "s1",
                "feature_timestamp": naive,
                **{c: 1.0 for c in ONLINE_SELLER_FEATURES},
            }
        ]
    )
    client = FeastSellerClient(freshness_sla_hours=36)
    monkeypatch.setattr(client, "_get_store", lambda: _FakeStore(frame))
    row = client.get_online_features(["s1"], now=now)[0]
    assert row.stale is False
    assert row.feature_timestamp is not None
    assert row.feature_timestamp.tzinfo is not None


def test_warmup_trips_circuit_and_skips_later_lookups(monkeypatch) -> None:
    """An unmaterialized repo must not rebuild the registry on every predict."""
    client = FeastSellerClient()
    calls = {"n": 0}

    def boom() -> None:
        calls["n"] += 1
        raise RuntimeError("no registry")

    monkeypatch.setattr(client, "_get_store", boom)
    assert client.warm() is False
    assert client.available is False
    assert client.get_online_features(["s1"]) == []
    assert calls["n"] == 1  # lookup must not retry store construction


def test_lookup_trips_circuit_on_unserviceable_repo(monkeypatch) -> None:
    client = FeastSellerClient()

    def boom() -> None:
        raise RuntimeError("missing feature service")

    monkeypatch.setattr(client, "_get_store", boom)
    assert client.get_online_features(["s1"]) == []
    assert client.available is False

    def must_not_retry() -> None:
        raise AssertionError("circuit breaker should skip store rebuild")

    monkeypatch.setattr(client, "_get_store", must_not_retry)
    assert client.get_online_features(["s1"]) == []


def test_empty_seller_ids_short_circuit() -> None:
    client = FeastSellerClient()
    client._unavailable = True
    assert client.get_online_features([]) == []


def test_hydrate_fails_open_when_circuit_is_tripped() -> None:
    """A dead online store must not raise on the predict path."""
    from olist_ml.config import Settings
    from olist_ml.inference.predictor import PredictionService
    from olist_ml.schemas import PredictRequest

    now = datetime.now(tz=UTC)
    settings = Settings(feast_online_enabled=True)
    service = PredictionService(settings)
    assert service.feast_client is not None
    service.feast_client._unavailable = True
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
    assert stale is True
    assert filled.seller_order_count_30d is None
    assert filled.order_id == "o"


def test_load_warms_feast_during_startup(tmp_path, monkeypatch) -> None:
    """Registry construction belongs in load() (startup probe), not first predict."""
    from olist_ml.config import Settings
    from olist_ml.inference.predictor import PredictionService
    from olist_ml.training.package import ModelMeta

    model_path = tmp_path / "model.joblib"
    meta_path = tmp_path / "model_meta.json"
    model_path.write_bytes(b"stub")
    meta_path.write_text("{}", encoding="utf-8")
    settings = Settings(
        feast_online_enabled=True,
        model_path=model_path,
        model_meta_path=meta_path,
    )
    meta = ModelMeta(
        model_version="v1",
        trained_at="t",
        feature_names=["f"],
        best_params={},
        metrics={},
    )
    monkeypatch.setattr(
        "olist_ml.inference.predictor.load_artifact",
        lambda *args, **kwargs: (object(), meta),
    )
    service = PredictionService(settings)
    assert service.feast_client is not None
    warmed: list[bool] = []
    service.feast_client.warm = lambda: warmed.append(True) or True
    service.load()
    assert warmed == [True]


def test_serving_store_resolves_paths_relative_to_config_file(tmp_path, monkeypatch) -> None:
    """Feast resolves store paths against CWD; serving must anchor to the yaml."""
    pytest.importorskip("feast")
    import feast

    repo = tmp_path / "app" / "feature_repo"
    repo.mkdir(parents=True)
    config_path = repo / "feature_store.serving.yaml"
    config_path.write_text(
        "project: olist_ml\n"
        "provider: local\n"
        "registry:\n"
        "  registry_type: file\n"
        "  path: ../data/feast/registry.db\n"
        "online_store:\n"
        "  type: sqlite\n"
        "  path: ../data/feast/online.db\n"
        "entity_key_serialization_version: 3\n",
        encoding="utf-8",
    )
    captured: dict = {}

    class FakeRepoConfig:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            captured.update(kwargs)

    class FakeFeatureStore:
        def __init__(self, config=None, repo_path=None) -> None:  # noqa: ANN001
            captured["passed_config"] = config

    monkeypatch.setattr(feast, "RepoConfig", FakeRepoConfig)
    monkeypatch.setattr(feast, "FeatureStore", FakeFeatureStore)
    monkeypatch.chdir(tmp_path)  # CWD-relative resolve would miss the baked store

    client = FeastSellerClient(repo_path=repo, serving_config=config_path)
    client._serving_store()

    expected_registry = str((repo / "../data/feast/registry.db").resolve())
    expected_online = str((repo / "../data/feast/online.db").resolve())
    assert captured["registry"]["path"] == expected_registry
    assert captured["online_store"]["path"] == expected_online
    cwd_wrong = str((tmp_path / "data" / "feast" / "registry.db").resolve())
    assert captured["registry"]["path"] != cwd_wrong
