"""Warehouse snapshot export still writes incomplete files so the trainer can refuse them."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]

pytest.importorskip("google.cloud.bigquery", reason="export talks to BigQuery")
pytest.importorskip("pyarrow", reason="parquet round-trip needs pyarrow")


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "export_training_snapshot", ROOT / "scripts/export_training_snapshot.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_writes_incomplete_snapshot_for_inspection(tmp_path: Path) -> None:
    export = _load_module()
    frame = pd.DataFrame({"seller_id": ["s1"]})  # missing contract columns
    client = MagicMock()
    client.query.return_value.to_dataframe.return_value = frame
    out = tmp_path / "fct_training_snapshot.parquet"

    with patch("google.cloud.bigquery.Client", return_value=client):
        written = export.export_snapshot("my-proj", out)

    assert written == out
    sql = client.query.call_args.args[0]
    assert sql == "select * from `my-proj.ml.fct_training_snapshot`"
    loaded = pd.read_parquet(out)
    assert list(loaded["seller_id"]) == ["s1"]
    assert "promise_miss" not in loaded.columns


def test_export_limit_is_integer_interpolated(tmp_path: Path) -> None:
    export = _load_module()
    client = MagicMock()
    client.query.return_value.to_dataframe.return_value = pd.DataFrame({"seller_id": []})
    out = tmp_path / "snap.parquet"
    with patch("google.cloud.bigquery.Client", return_value=client):
        export.export_snapshot("p", out, dataset="ml", table="fct_training_snapshot", limit=25)
    sql = client.query.call_args.args[0]
    assert sql.endswith("limit 25")
    assert "limit 25.0" not in sql
