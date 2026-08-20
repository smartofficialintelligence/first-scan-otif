"""Ingest stages raw CSVs through GCS before loading BigQuery (mocked)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytest.importorskip("google.cloud.storage", reason="ingest needs the gcp extra")


def _load_module():
    spec = importlib.util.spec_from_file_location("ingest_olist", ROOT / "scripts/ingest_olist.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bucket_name_matches_terraform():
    ingest = _load_module()
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("GCS_RAW_BUCKET", None)
        assert ingest.raw_bucket_name("my-proj") == "olist-ml-raw-my-proj"


def test_bucket_name_env_override():
    ingest = _load_module()
    with patch.dict("os.environ", {"GCS_RAW_BUCKET": "custom-bucket"}):
        assert ingest.raw_bucket_name("my-proj") == "custom-bucket"


def test_upload_writes_every_required_csv():
    ingest = _load_module()
    blob = MagicMock()
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket

    with patch.object(ingest.storage, "Client", return_value=client):
        uris = ingest.upload_raw_to_gcs(ROOT / "data/fixtures", "proj", "bkt")

    assert blob.upload_from_filename.call_count == len(ingest.REQUIRED_FILES)
    assert all(uri.startswith("gs://bkt/olist/") for uri in uris.values())


def test_load_reads_from_gcs_uris_not_dataframes():
    ingest = _load_module()
    client = MagicMock()
    client.get_table.return_value = MagicMock(num_rows=7)

    with patch.object(ingest.bigquery, "Client", return_value=client):
        ingest.load_to_bq({"orders": "gs://bkt/olist/olist_orders_dataset.csv"}, "proj")

    assert client.load_table_from_uri.called
    assert not client.load_table_from_dataframe.called
    uri = client.load_table_from_uri.call_args.args[0]
    assert uri.startswith("gs://")
    job_config = client.load_table_from_uri.call_args.kwargs["job_config"]
    assert job_config.skip_leading_rows == 1
    assert job_config.write_disposition == ingest.bigquery.WriteDisposition.WRITE_TRUNCATE
    assert job_config.autodetect is not True
    assert job_config.schema  # header names must stay explicit, not string_field_N


def test_upload_raises_when_required_csv_is_missing(tmp_path):
    ingest = _load_module()
    blob = MagicMock()
    bucket = MagicMock()
    bucket.blob.return_value = blob
    client = MagicMock()
    client.bucket.return_value = bucket
    with patch.object(ingest.storage, "Client", return_value=client), pytest.raises(FileNotFoundError):
        ingest.upload_raw_to_gcs(tmp_path, "proj", "bkt")
