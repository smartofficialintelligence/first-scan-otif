"""H6 champion swap is an explicit human action, never an implicit train side-effect."""

from __future__ import annotations

import json
import os

import pytest

from olist_ml.config import Settings
from olist_ml.training.promote import (
    latest_candidate_version,
    promote_candidate,
)


def _settings(tmp_path) -> Settings:
    return Settings(
        artifact_dir=tmp_path,
        model_path=tmp_path / "champion" / "model.joblib",
        model_meta_path=tmp_path / "champion" / "model_meta.json",
    )


def _write_candidate(tmp_path, version: str, *, payload: bytes = b"model-v") -> None:
    root = tmp_path / "candidates" / version
    root.mkdir(parents=True)
    (root / "model.joblib").write_bytes(payload)
    (root / "model_meta.json").write_text(
        json.dumps({"model_version": version}),
        encoding="utf-8",
    )


def test_promote_requires_named_approver(tmp_path) -> None:
    _write_candidate(tmp_path, "v1")
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="approved_by"):
        promote_candidate(settings, "v1", approved_by="")
    with pytest.raises(ValueError, match="approved_by"):
        promote_candidate(settings, "v1", approved_by="   ")
    assert not settings.model_path.exists()


def test_promote_missing_candidate_raises(tmp_path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(FileNotFoundError, match="No candidates"):
        promote_candidate(settings, approved_by="alice")
    _write_candidate(tmp_path, "v1")
    with pytest.raises(FileNotFoundError, match="incomplete"):
        promote_candidate(settings, "v-missing", approved_by="alice")


def test_promote_copies_candidate_and_records_approver(tmp_path) -> None:
    _write_candidate(tmp_path, "v1", payload=b"champion-bytes")
    settings = _settings(tmp_path)
    record = promote_candidate(settings, "v1", approved_by=" alice ", note="canary ok")
    assert settings.model_path.read_bytes() == b"champion-bytes"
    assert json.loads(settings.model_meta_path.read_text())["model_version"] == "v1"
    assert record["approved_by"] == "alice"
    assert record["promoted_version"] == "v1"
    assert record["previous_champion"] is None
    lines = (tmp_path / "promote_record.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["approved_by"] == "alice"


def test_promote_survives_corrupt_previous_champion_meta(tmp_path) -> None:
    _write_candidate(tmp_path, "v2")
    settings = _settings(tmp_path)
    settings.model_meta_path.parent.mkdir(parents=True)
    settings.model_meta_path.write_text("{not-json", encoding="utf-8")
    record = promote_candidate(settings, "v2", approved_by="bob")
    assert record["previous_champion"] is None
    assert record["promoted_version"] == "v2"


def test_latest_candidate_is_newest_mtime(tmp_path) -> None:
    _write_candidate(tmp_path, "older")
    _write_candidate(tmp_path, "newer")
    os.utime(tmp_path / "candidates" / "older", (1_000_000, 1_000_000))
    os.utime(tmp_path / "candidates" / "newer", (2_000_000, 2_000_000))
    assert latest_candidate_version(_settings(tmp_path)) == "newer"
