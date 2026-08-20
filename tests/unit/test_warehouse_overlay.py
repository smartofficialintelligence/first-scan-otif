"""Warehouse inputs to the champion training table.

The point of these tests is the leakage guard: the Feast overlay must join on
(seller_id, handoff_ts), never on seller_id alone. A seller-only join would put
a seller's latest history onto their earlier orders.
"""

from __future__ import annotations

import pandas as pd
import pytest

from olist_ml.config import Settings
from olist_ml.features.contracts import FEATURE_COLUMNS, TARGET_COLUMN
from olist_ml.features.historical import (
    SNAPSHOT_DBT,
    SNAPSHOT_FEAST,
    SNAPSHOT_PANDAS,
    apply_warehouse_features,
)

pytest.importorskip("pyarrow", reason="parquet round-trip needs pyarrow")


def _settings(tmp_path) -> Settings:
    return Settings(artifact_dir=tmp_path)


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "seller_id": ["s1", "s1", "s2"],
            "handoff_ts": pd.to_datetime(
                ["2018-01-01", "2018-06-01", "2018-01-01"], utc=True
            ),
            "seller_late_rate_7d": [0.0, 0.0, 0.0],
            "seller_order_count_7d": [1.0, 1.0, 1.0],
        }
    )


def test_no_artifacts_falls_back_to_pandas(tmp_path):
    result = apply_warehouse_features(_features(), _settings(tmp_path))
    assert result.snapshot_id == SNAPSHOT_PANDAS
    assert result.overlay_rows == 0


def test_feast_overlay_is_point_in_time_not_seller_wide(tmp_path):
    """The later order of the same seller must NOT inherit the earlier value."""
    pd.DataFrame(
        {
            "seller_id": ["s1"],
            "event_timestamp": pd.to_datetime(["2018-01-01"], utc=True),
            "seller_late_rate_7d": [0.77],
        }
    ).to_parquet(tmp_path / "feast_historical.parquet", index=False)

    result = apply_warehouse_features(_features(), _settings(tmp_path))

    assert result.snapshot_id == SNAPSHOT_FEAST
    assert result.overlay_rows == 1
    frame = result.frame.sort_values(["seller_id", "handoff_ts"]).reset_index(drop=True)
    assert frame.loc[0, "seller_late_rate_7d"] == pytest.approx(0.77)  # exact match
    assert frame.loc[1, "seller_late_rate_7d"] == pytest.approx(0.0)  # same seller, later
    assert frame.loc[2, "seller_late_rate_7d"] == pytest.approx(0.0)  # other seller


def test_feast_overlay_does_not_duplicate_rows(tmp_path):
    """Duplicate entity rows must not fan out the training table."""
    pd.DataFrame(
        {
            "seller_id": ["s1", "s1"],
            "event_timestamp": pd.to_datetime(["2018-01-01", "2018-01-01"], utc=True),
            "seller_late_rate_7d": [0.5, 0.77],
        }
    ).to_parquet(tmp_path / "feast_historical.parquet", index=False)

    result = apply_warehouse_features(_features(), _settings(tmp_path))
    assert len(result.frame) == 3


def test_incomplete_dbt_snapshot_is_refused(tmp_path):
    """A snapshot missing contract columns must not silently train."""
    pd.DataFrame({"seller_id": ["s1"], "handoff_ts": [pd.Timestamp("2018-01-01", tz="UTC")]}).to_parquet(
        tmp_path / "fct_training_snapshot.parquet", index=False
    )
    result = apply_warehouse_features(_features(), _settings(tmp_path))
    assert result.snapshot_id == SNAPSHOT_PANDAS


def test_complete_dbt_snapshot_replaces_training_table(tmp_path):
    row = {col: 0.0 for col in FEATURE_COLUMNS}
    row.update(
        {
            "seller_id": "s9",
            "handoff_ts": pd.Timestamp("2018-03-01", tz="UTC"),
            TARGET_COLUMN: 0,
        }
    )
    pd.DataFrame([row]).to_parquet(tmp_path / "fct_training_snapshot.parquet", index=False)

    result = apply_warehouse_features(_features(), _settings(tmp_path))
    assert result.snapshot_id == SNAPSHOT_DBT
    assert list(result.frame["seller_id"]) == ["s9"]
