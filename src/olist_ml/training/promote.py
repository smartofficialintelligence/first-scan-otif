"""Explicit candidate → champion promotion (H6).

Training writes candidates under ``artifacts/candidates/<version>/``; nothing
else touches the champion path serving loads. This module is the only code
that copies a candidate onto ``settings.model_path`` — and it records who
approved the swap.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from olist_ml.config import Settings
from olist_ml.logging import get_logger

logger = get_logger(__name__)

PROMOTE_RECORD = "promote_record.jsonl"


def candidates_root(settings: Settings) -> Path:
    return settings.artifact_dir / "candidates"


def candidate_paths(settings: Settings, model_version: str) -> tuple[Path, Path]:
    root = candidates_root(settings) / model_version
    return root / "model.joblib", root / "model_meta.json"


def latest_candidate_version(settings: Settings) -> str | None:
    root = candidates_root(settings)
    if not root.exists():
        return None
    dirs = [d for d in root.iterdir() if d.is_dir() and (d / "model_meta.json").exists()]
    if not dirs:
        return None
    return max(dirs, key=lambda d: d.stat().st_mtime).name


def promote_candidate(
    settings: Settings,
    model_version: str | None = None,
    *,
    approved_by: str,
    note: str = "",
) -> dict[str, object]:
    """Copy one trained candidate onto the champion path. Requires a named approver."""
    if not approved_by or not approved_by.strip():
        raise ValueError("promote requires approved_by (H6 — a person owns the swap)")
    version = model_version or latest_candidate_version(settings)
    if version is None:
        raise FileNotFoundError(f"No candidates under {candidates_root(settings)}")
    cand_model, cand_meta = candidate_paths(settings, version)
    if not cand_model.exists() or not cand_meta.exists():
        raise FileNotFoundError(f"Candidate artifact incomplete: {cand_model.parent}")

    previous = None
    if settings.model_meta_path.exists():
        try:
            previous = json.loads(settings.model_meta_path.read_text(encoding="utf-8")).get(
                "model_version"
            )
        except (OSError, json.JSONDecodeError):
            previous = None

    settings.model_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cand_model, settings.model_path)
    shutil.copy2(cand_meta, settings.model_meta_path)

    record = {
        "promoted_version": version,
        "previous_champion": previous,
        "approved_by": approved_by.strip(),
        "note": note,
        "promoted_at": datetime.now(UTC).isoformat(),
        "champion_model_path": str(settings.model_path),
    }
    record_path = settings.artifact_dir / PROMOTE_RECORD
    with record_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    logger.info(
        "Promoted %s -> %s (approved_by=%s, previous=%s)",
        version,
        settings.model_path,
        approved_by,
        previous,
    )
    return record
