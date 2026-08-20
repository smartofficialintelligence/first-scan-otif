"""Champion training records provenance and lands in the MLflow registry.

Before this, `make train-local` produced the deployed champion while MLflow only
ever saw candidates from `make train-pipeline` — so the shipped model had no run
behind it, and git_sha / snapshot_id were null on every artifact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from olist_ml.config import Settings
from olist_ml.features.historical import SNAPSHOT_PANDAS
from olist_ml.training.pipeline import mlflow_tracking_uri, run_training

pytest.importorskip("mlflow", reason="registry lineage needs the ml extra")

FIXTURES = Path(__file__).resolve().parents[2] / "data/fixtures"


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    """One fixture-sized training run into an isolated artifact dir."""
    artifact_dir = tmp_path_factory.mktemp("artifacts")
    settings = Settings(artifact_dir=artifact_dir, n_optuna_trials=1, cv_folds=2)
    meta = run_training(settings, data_dir=FIXTURES)
    return meta, settings


def test_meta_records_git_sha_and_snapshot(trained):
    meta, _ = trained
    assert meta.snapshot_id == SNAPSHOT_PANDAS
    # git_sha is None outside a git checkout (e.g. an exported tarball); when
    # present it must look like a real SHA rather than a placeholder.
    if meta.git_sha is not None:
        assert len(meta.git_sha) >= 7
        assert meta.git_sha.isalnum()


def test_tracking_uri_is_scoped_to_the_artifact_dir(trained):
    _, settings = trained
    uri = mlflow_tracking_uri(settings)
    assert uri.startswith("sqlite:///")
    assert str(settings.artifact_dir) in uri


def test_run_is_registered_as_a_candidate(trained):
    import mlflow
    from mlflow.tracking import MlflowClient

    meta, settings = trained
    mlflow.set_tracking_uri(mlflow_tracking_uri(settings))
    client = MlflowClient()

    versions = client.search_model_versions("name='olist-late-delivery'")
    assert versions, "training did not register a model version"

    run = client.get_run(versions[0].run_id)
    tags = run.data.tags
    assert tags["lifecycle_state"] == "REGISTERED_CANDIDATE"
    assert tags["model_version"] == meta.model_version
    assert tags["snapshot_id"] == SNAPSHOT_PANDAS
    assert "git_sha" in tags


def test_training_can_skip_registration_for_the_pipeline_path(tmp_path):
    """pipelines/components.py registers once itself — training must not double."""
    settings = Settings(artifact_dir=tmp_path, n_optuna_trials=1, cv_folds=2)
    meta = run_training(settings, data_dir=FIXTURES, register_mlflow=False)
    assert meta.model_version
    assert not (tmp_path / "mlflow.db").exists()
