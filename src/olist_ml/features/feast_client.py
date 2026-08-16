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
    ) -> None:
        self.repo_path = Path(repo_path)
        self.freshness_sla_hours = freshness_sla_hours
        self.feature_service = feature_service
        self._store: Any | None = None

    def _get_store(self) -> Any:
        if self._store is None:
            from feast import FeatureStore

            self._store = FeatureStore(repo_path=str(self.repo_path))
        return self._store

    def get_online_features(
        self,
        seller_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> list[SellerFeatureRow]:
        if not seller_ids:
            return []
        store = self._get_store()
        entity_rows = [{"seller_id": sid} for sid in seller_ids]
        response = store.get_online_features(
            features=store.get_feature_service(self.feature_service),
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
