"""Feast adapters for online seller feature lookup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from olist_ml.features.contracts import ONLINE_SELLER_FEATURES
from olist_ml.logging import get_logger

logger = get_logger(__name__)

DEFAULT_FEAST_REPO = Path("feature_repo")
DEFAULT_SERVING_CONFIG = "feature_store.serving.yaml"


@dataclass(frozen=True)
class SellerFeatureRow:
    seller_id: str
    features: dict[str, float]
    feature_timestamp: datetime | None
    stale: bool


class FeastSellerClient:
    """Thin wrapper around Feast online store for seller_liveness_v1."""

    def __init__(
        self,
        repo_path: Path | str = DEFAULT_FEAST_REPO,
        freshness_sla_hours: int = 36,
        feature_service: str = "seller_online_v1",
        serving_config: Path | str | None = None,
    ) -> None:
        self.repo_path = Path(repo_path)
        self.freshness_sla_hours = freshness_sla_hours
        self.feature_service = feature_service
        # Serving reads the online store only. feature_store.yaml names the
        # BigQuery offline store for apply/materialize, and Feast imports that
        # driver eagerly — which a serving container does not install. The
        # serving config is the same registry and online store, minus the
        # offline block, so local and container behave identically.
        self.serving_config = (
            Path(serving_config)
            if serving_config is not None
            else self.repo_path / DEFAULT_SERVING_CONFIG
        )
        self._store: Any | None = None
        # Tripped when the repo cannot serve (never materialized, missing
        # feature service, feast not installed). Rebuilding the registry costs
        # seconds, so retrying per request would put that on p95 latency for
        # every prediction. Trip once, log once, fall back to request values.
        self._unavailable = False

    @property
    def available(self) -> bool:
        return not self._unavailable

    def _trip(self, reason: str, exc: Exception) -> None:
        self._unavailable = True
        self._store = None
        logger.warning(
            "Feast online store unavailable (%s: %s) — serving on request values "
            "and cold-start defaults for the rest of this process. Run "
            "`make feast-apply` (BigQuery) or `make feast-materialize-local` ($0) "
            "to populate %s.",
            reason,
            exc,
            self.repo_path,
        )

    def _serving_store(self) -> Any:
        """Build the store from the serving config, resolving paths ourselves.

        Feast resolves relative store paths against the process working
        directory, not the config file, so a container started from anywhere
        would miss the registry. The yaml's paths are relative to the config
        file (feature_repo/../data/feast); anchor them there and hand Feast
        absolute paths.
        """
        import yaml
        from feast import FeatureStore, RepoConfig

        raw = yaml.safe_load(self.serving_config.read_text(encoding="utf-8")) or {}
        base = self.serving_config.parent

        def _abs(value: str) -> str:
            path = Path(value)
            return str(path if path.is_absolute() else (base / path).resolve())

        registry = dict(raw.get("registry") or {})
        registry["path"] = _abs(str(registry.get("path", "../data/feast/registry.db")))
        online = dict(raw.get("online_store") or {})
        online["path"] = _abs(str(online.get("path", "../data/feast/online.db")))

        config = RepoConfig(
            project=raw.get("project", "olist_ml"),
            provider=raw.get("provider", "local"),
            registry=registry,
            online_store=online,
            entity_key_serialization_version=raw.get("entity_key_serialization_version", 3),
        )
        return FeatureStore(config=config)

    def _get_store(self) -> Any:
        if self._store is None:
            from feast import FeatureStore

            if self.serving_config.exists():
                self._store = self._serving_store()
            else:
                self._store = FeatureStore(repo_path=str(self.repo_path))
        return self._store

    def warm(self) -> bool:
        """Build the store at startup so no user request pays registry load.

        Feast spends seconds constructing a registry the first time. On Cloud
        Run with min-instances 0 that would land on the first request after a
        cold start; called from PredictionService.load() it lands inside the
        startup probe instead. Returns False when the repo cannot serve.
        """
        if self._unavailable:
            return False
        try:
            store = self._get_store()
            store.get_feature_service(self.feature_service)
        except Exception as exc:
            self._trip("warmup failed", exc)
            return False
        logger.info("Feast online store ready (repo=%s)", self.repo_path)
        return True

    def get_online_features(
        self,
        seller_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> list[SellerFeatureRow]:
        if not seller_ids or self._unavailable:
            return []
        try:
            store = self._get_store()
            service = store.get_feature_service(self.feature_service)
        except Exception as exc:  # import error, no registry, no such service
            self._trip("repo not serviceable", exc)
            return []
        entity_rows = [{"seller_id": sid} for sid in seller_ids]
        response = store.get_online_features(
            features=service,
            entity_rows=entity_rows,
        )
        frame = response.to_df()
        now = now or datetime.now(tz=UTC)
        rows: list[SellerFeatureRow] = []
        for _, row in frame.iterrows():
            feats: dict[str, float] = {}
            for name in ONLINE_SELLER_FEATURES:
                val = row.get(name)
                feats[name] = float(val) if pd.notna(val) else 0.0
            ts_raw = row.get("feature_timestamp", row.get("event_timestamp"))
            ts: datetime | None = None
            if ts_raw is not None and not pd.isna(ts_raw):
                # Feast UnixTimestamp may surface as epoch seconds or datetime.
                if isinstance(ts_raw, (int, float)):
                    ts = datetime.fromtimestamp(float(ts_raw), tz=UTC)
                else:
                    ts = pd.Timestamp(ts_raw).to_pydatetime()
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
            stale = True
            if ts is not None:
                age_h = (now - ts).total_seconds() / 3600.0
                stale = age_h > self.freshness_sla_hours
            rows.append(
                SellerFeatureRow(
                    seller_id=str(row["seller_id"]),
                    features=feats,
                    feature_timestamp=ts,
                    stale=stale,
                )
            )
        return rows
