"""Warehouse (dbt / Feast) inputs to the champion training table.

The pandas builder (:mod:`olist_ml.features.build`) is always the base. When the
warehouse path has actually produced artifacts, training *consumes* them instead
of exporting them and ignoring them:

1. **dbt training snapshot** — a parquet export of ``ml.fct_training_snapshot``
   replaces the training table outright (the warehouse defined every column).
2. **Feast historical retrieval** — ``artifacts/feast_historical.parquet``
   overlays point-in-time seller history onto the pandas rows.
3. Neither present → pandas only, exactly as before.

Point-in-time safety
--------------------
The Feast overlay joins on ``(seller_id, handoff_ts)``, never on ``seller_id``
alone. ``get_historical_features`` builds each parquet row from an entity row
whose ``event_timestamp`` *is* that order's ``handoff_ts``, so an exact-key join
returns the same value Feast computed as-of that scan. A seller-only join would
attach a seller's latest history to their earlier orders — future information
about the label window — and is the leak this module exists to avoid.

Overlaid values only ever fill the six ``ONLINE_SELLER_FEATURES``; nothing else
is touched, and rows without a warehouse match keep their pandas values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from olist_ml.config import Settings
from olist_ml.features.contracts import (
    FEATURE_COLUMNS,
    ONLINE_SELLER_FEATURES,
    TARGET_COLUMN,
)
from olist_ml.logging import get_logger

logger = get_logger(__name__)

SNAPSHOT_PANDAS = "pandas_builder"
SNAPSHOT_DBT = "dbt_fct_training_snapshot"
SNAPSHOT_FEAST = "feast_historical"

SNAPSHOT_ENV = "TRAINING_SNAPSHOT_PATH"
FEAST_HISTORICAL_ENV = "FEAST_HISTORICAL_PATH"

SNAPSHOT_FILENAME = "fct_training_snapshot.parquet"
FEAST_HISTORICAL_FILENAME = "feast_historical.parquet"

JOIN_KEYS = ("seller_id", "handoff_ts")


@dataclass(frozen=True)
class WarehouseResult:
    """Training table plus the provenance recorded on the model artifact."""

    frame: pd.DataFrame
    snapshot_id: str
    overlay_rows: int = 0


def _resolve(env_var: str, filename: str, settings: Settings) -> Path:
    override = os.environ.get(env_var, "").strip()
    if override:
        return Path(override)
    return settings.artifact_dir / filename


def _read_parquet(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:  # missing pyarrow, corrupt file — never break training
        logger.exception("Unreadable warehouse parquet at %s; falling back", path)
        return None


def _snapshot_is_usable(frame: pd.DataFrame) -> bool:
    """A snapshot may replace the training table only if it is complete."""
    required = {"handoff_ts", TARGET_COLUMN, *FEATURE_COLUMNS}
    missing = required - set(frame.columns)
    if missing:
        logger.warning(
            "dbt snapshot ignored — missing %d required columns (e.g. %s)",
            len(missing),
            sorted(missing)[:5],
        )
        return False
    if frame.empty:
        logger.warning("dbt snapshot ignored — zero rows")
        return False
    return True


def _normalize_join_frame(frame: pd.DataFrame, time_col: str) -> pd.DataFrame | None:
    if "seller_id" not in frame.columns or time_col not in frame.columns:
        return None
    out = frame.copy()
    out["seller_id"] = out["seller_id"].astype(str)
    out[time_col] = pd.to_datetime(out[time_col], utc=True, errors="coerce")
    return out.dropna(subset=[time_col])


def _overlay_feast(features: pd.DataFrame, historical: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Fill ONLINE_SELLER_FEATURES from a PIT-correct Feast retrieval."""
    available = [c for c in ONLINE_SELLER_FEATURES if c in historical.columns]
    if not available:
        logger.warning("Feast historical parquet has no online seller columns; skipping overlay")
        return features, 0

    left = _normalize_join_frame(features, "handoff_ts")
    right = _normalize_join_frame(historical, "event_timestamp")
    if left is None or right is None:
        logger.warning("Feast overlay skipped — join keys absent (need seller_id + timestamps)")
        return features, 0

    right = right.rename(columns={"event_timestamp": "handoff_ts"})
    # One row per (seller, scan): duplicate entity rows would fan out the join.
    right = right.drop_duplicates(subset=list(JOIN_KEYS), keep="last")
    right = right[[*JOIN_KEYS, *available]]

    merged = left.merge(right, on=list(JOIN_KEYS), how="left", suffixes=("", "_feast"))
    matched = 0
    for col in available:
        incoming = merged[f"{col}_feast"]
        matched = max(matched, int(incoming.notna().sum()))
        merged[col] = incoming.where(incoming.notna(), merged[col])
    merged = merged.drop(columns=[f"{col}_feast" for col in available])

    if matched == 0:
        logger.warning(
            "Feast historical parquet matched 0 rows on (seller_id, handoff_ts) — "
            "keeping pandas values"
        )
    return merged, matched


def apply_warehouse_features(features: pd.DataFrame, settings: Settings) -> WarehouseResult:
    """Return the training table plus its provenance id.

    Precedence: dbt snapshot → Feast overlay → pandas only.
    """
    snapshot_path = _resolve(SNAPSHOT_ENV, SNAPSHOT_FILENAME, settings)
    snapshot = _read_parquet(snapshot_path)
    if snapshot is not None and _snapshot_is_usable(snapshot):
        logger.info(
            "Training on dbt warehouse snapshot rows=%d path=%s",
            len(snapshot),
            snapshot_path,
        )
        return WarehouseResult(snapshot, SNAPSHOT_DBT, len(snapshot))

    historical_path = _resolve(FEAST_HISTORICAL_ENV, FEAST_HISTORICAL_FILENAME, settings)
    historical = _read_parquet(historical_path)
    if historical is not None and not historical.empty:
        overlaid, matched = _overlay_feast(features, historical)
        if matched:
            logger.info(
                "Feast historical overlay applied rows=%d/%d path=%s",
                matched,
                len(features),
                historical_path,
            )
            return WarehouseResult(overlaid, SNAPSHOT_FEAST, matched)

    logger.info("No warehouse artifacts consumed; training on the pandas builder")
    return WarehouseResult(features, SNAPSHOT_PANDAS, 0)
