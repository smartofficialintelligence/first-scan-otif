"""Unit tests for offline gates and MLflow candidate registration (file store)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pytest

from olist_ml.registry.mlflow_registry import (
    LIFECYCLE_REGISTERED_CANDIDATE,
    get_candidate_info,
    log_and_register_candidate,
)
from olist_ml.training.gates import offline_promotion_checks
from olist_ml.training.package import ModelMeta


def test_offline_gates_pass_without_champion() -> None:
    result = offline_promotion_checks({"pr_auc": 0.42})
    assert result["passed"] is True
    assert any("no champion" in r for r in result["reasons"])


def test_offline_gates_fail_missing_pr_auc() -> None:
    result = offline_promotion_checks({"brier": 0.1})
    assert result["passed"] is False
    assert "missing candidate pr_auc" in result["reasons"][0]


def test_offline_gates_pr_auc_within_tolerance() -> None:
    ok = offline_promotion_checks(
        {"test_pr_auc": 0.55},
        {"test_pr_auc": 0.56},
    )
    assert ok["passed"] is True

    bad = offline_promotion_checks(
        {"pr_auc": 0.50},
        {"pr_auc": 0.56},
    )
    assert bad["passed"] is False
    assert any("PR-AUC" in r for r in bad["reasons"])


def test_offline_gates_brier_and_ece() -> None:
    result = offline_promotion_checks(
        {"pr_auc": 0.60, "brier": 0.20, "ece": 0.05},
        {"pr_auc": 0.60, "brier": 0.10, "ece": 0.04},
    )
    assert result["passed"] is False
    assert any("Brier" in r for r in result["reasons"])


class _StubBundle:
    """Module-level picklable stand-in with predict_proba."""

    def predict_proba(self, X):  # noqa: ANN001, ANN201, N803
        import numpy as np

        n = len(X)
        return np.column_stack([np.zeros(n), np.full(n, 0.5)])


def test_log_and_register_candidate_file_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_path = tmp_path / "model.joblib"
    meta_path = tmp_path / "model_meta.json"
    joblib.dump(_StubBundle(), model_path)
    meta = ModelMeta(
        model_version="test-20200101T000000Z",
        trained_at="2020-01-01T00:00:00+00:00",
        feature_names=["f1"],
        best_params={"max_depth": 3},
        metrics={"test_pr_auc": 0.5, "valid_pr_auc": 0.51},
        n_train=10,
        n_valid=5,
        n_test=5,
    )
    meta_path.write_text(json.dumps(meta.__dict__), encoding="utf-8")

    tracking = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking)

    run_id = log_and_register_candidate(meta, model_path, meta_path, tracking_uri=tracking)
    assert run_id
    info = get_candidate_info(run_id, tracking_uri=tracking)
    assert info["run_id"] == run_id
    assert info["lifecycle_state"] == LIFECYCLE_REGISTERED_CANDIDATE
    assert info["model_version"] == meta.model_version
    assert "test_pr_auc" in info["metrics"]
