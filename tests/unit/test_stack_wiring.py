"""Contract tests: the named stack must stay wired to the deployed path.

Each assertion here failed at some point in this repo's history — the tools were
named in the README while the serving image, the Cloud Run service, or the
champion training run did not actually use them. These tests exist so that
regression is a red build rather than a claim nobody can verify.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return (ROOT / "Dockerfile").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def cloud_run_tf() -> str:
    return (ROOT / "terraform/modules/cloud_run/main.tf").read_text(encoding="utf-8")


def test_serving_image_installs_feast_and_agent(dockerfile):
    """Feast and LangGraph are named in the README stack, so they must ship."""
    sync = [line for line in dockerfile.splitlines() if "uv sync" in line]
    assert sync, "no uv sync in Dockerfile"
    line = sync[0]
    assert "--extra feast" in line, "serving image would have no Feast client"
    assert "--extra agent" in line, "serving image would 503 on /v1/agent/review"


def test_serving_image_carries_feature_repo_and_online_store(dockerfile):
    assert "COPY feature_repo" in dockerfile
    assert "COPY data/feast" in dockerfile


def test_serving_config_has_no_offline_store():
    """Feast eagerly imports the offline driver; serving must not name one."""
    import yaml

    raw = yaml.safe_load((ROOT / "feature_repo/feature_store.serving.yaml").read_text())
    assert "offline_store" not in raw, "serving container would need BigQuery deps"
    assert raw["online_store"]["type"] == "sqlite"


def test_cloud_run_enables_feast(cloud_run_tf):
    assert "FEAST_ONLINE_ENABLED" in cloud_run_tf
    assert "FEAST_REPO_PATH" in cloud_run_tf


def test_feast_hydration_is_gated_off_pending_parity():
    """Wired but off: pandas and warehouse feature definitions disagree on ~10%
    of rows, so hydrating a pandas-trained model from the warehouse is skew.
    Flip this (and the Cloud Run env) together, once the definitions agree."""
    from olist_ml.config import Settings

    assert Settings().feast_online_enabled is False


def test_cloud_run_env_matches_the_gate(cloud_run_tf):
    """The service env must not re-enable what the default gates off."""
    assert 'value = "false"' in cloud_run_tf.split("FEAST_ONLINE_ENABLED")[1][:120]


def test_monitoring_module_defines_alert_policies():
    tf = (ROOT / "terraform/modules/monitoring/main.tf").read_text(encoding="utf-8")
    assert tf.count("google_monitoring_alert_policy") >= 2


def test_champion_training_registers_mlflow_by_default():
    """`make train-local` used to bypass MLflow, leaving champions unlineaged."""
    import inspect

    from olist_ml.training.pipeline import run_training

    assert inspect.signature(run_training).parameters["register_mlflow"].default is True


def test_ingest_stages_through_gcs():
    src = (ROOT / "scripts/ingest_olist.py").read_text(encoding="utf-8")
    assert "load_table_from_uri" in src, "BigQuery must load from the GCS object"
    assert "upload_from_filename" in src, "raw CSVs must land in the bucket"
    assert "load_table_from_dataframe" not in src, "that path bypasses the bucket"


def test_gated_pipeline_opts_out_of_training_registration():
    """pipelines/components.py registers once after gates; training must not also register."""
    import inspect

    from pipelines.components import run_train_steps

    src = inspect.getsource(run_train_steps)
    assert "register_mlflow=False" in src
