"""Serialize / load model artifacts with metadata."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

from olist_ml.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ModelMeta:
    model_version: str
    trained_at: str
    feature_names: list[str]
    best_params: dict[str, Any]
    metrics: dict[str, float]
    git_sha: str | None = None
    snapshot_id: str | None = None
    n_train: int | None = None
    n_valid: int | None = None
    n_test: int | None = None
    target: str = "promise_miss_at_handoff"
    p1_score_threshold: float | None = None
    p2_score_threshold: float | None = None
    p1_capacity: float = 0.025
    p2_capacity: float = 0.10


def save_artifact(
    pipeline: Any,
    meta: ModelMeta,
    *,
    model_path: Path,
    meta_path: Path,
) -> None:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    meta_path.write_text(json.dumps(asdict(meta), indent=2, sort_keys=True), encoding="utf-8")
    logger.info("Saved model=%s meta=%s", model_path, meta_path)


def load_artifact(model_path: Path, meta_path: Path) -> tuple[Any, ModelMeta]:
    pipeline = joblib.load(model_path)
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    allowed = {f.name for f in fields(ModelMeta)}
    meta = ModelMeta(**{k: v for k, v in raw.items() if k in allowed})
    return pipeline, meta


def new_model_version(prefix: str = "local") -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"
