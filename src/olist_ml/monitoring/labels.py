"""Delayed-label release (simulation contract)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from olist_ml.monitoring.logs import read_jsonl, write_jsonl


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value
    else:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def release_labels(
    rows: list[dict[str, Any]],
    *,
    virtual_now: datetime,
) -> tuple[list[dict[str, Any]], int]:
    """Set ``label_released`` where ``virtual_now >= label_release_at``.

    Returns ``(rows, n_released)``.
    """
    now = virtual_now if virtual_now.tzinfo else virtual_now.replace(tzinfo=UTC)
    released = 0
    out: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        release_at = _parse_ts(updated.get("label_release_at"))
        has_label = updated.get("label_promise_miss") is not None
        if release_at is not None and now >= release_at and has_label:
            updated["label_released"] = True
            released += 1
        else:
            updated["label_released"] = bool(updated.get("label_released"))
        out.append(updated)
    return out, released


def run_release_labels(
    *,
    log_path: Path,
    virtual_now: datetime,
    out_path: Path | None = None,
) -> dict[str, Any]:
    rows = read_jsonl(log_path)
    updated, n_released = release_labels(rows, virtual_now=virtual_now)
    dest = out_path or log_path
    write_jsonl(dest, updated)
    return {
        "log_path": str(dest),
        "virtual_now": virtual_now.isoformat(),
        "n_rows": len(updated),
        "n_released": n_released,
        "n_still_held": len(updated) - n_released,
    }
