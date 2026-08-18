"""H5 retrain-approval flag (file-backed; never implied by an alarm)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_H5_PATH = Path("artifacts/h5_retrain_approval.json")
DEFAULT_ALARM_PATH = Path("artifacts/drift_alarm.json")


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_h5_approval(
    *,
    approved: bool,
    approved_by: str,
    reason: str,
    path: Path = DEFAULT_H5_PATH,
) -> dict[str, Any]:
    body = {
        "approved": bool(approved),
        "approved_by": approved_by,
        "approved_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "gate": "H5",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    return body


def h5_is_approved(path: Path = DEFAULT_H5_PATH) -> bool:
    body = read_json(path)
    return bool(body and body.get("approved") is True)


def drift_alarm_active(path: Path = DEFAULT_ALARM_PATH) -> bool:
    body = read_json(path)
    return bool(body and body.get("alarm") is True)


def assert_retrain_allowed(
    *,
    reason: str,
    require_h5: bool = True,
    h5_path: Path = DEFAULT_H5_PATH,
    alarm_path: Path = DEFAULT_ALARM_PATH,
) -> None:
    """
    Retrain trigger contract:

    - ``drift``: alarm must be active AND H5 approved.
    - ``monthly``: H5 approved (schedule still does not auto-train without a human).
    - never auto-promote (caller must not set champion).
    """
    why = (reason or "").strip().lower()
    if require_h5 and not h5_is_approved(h5_path):
        raise PermissionError(
            "H5 retrain approval missing. Write artifacts/h5_retrain_approval.json "
            "(make approve-h5) before retrain_trigger."
        )
    if why == "drift" and not drift_alarm_active(alarm_path):
        raise PermissionError(
            "Retrain reason=drift requires an active drift alarm "
            f"at {alarm_path}."
        )
    if why not in {"drift", "monthly", "manual"}:
        raise ValueError(f"Unknown retrain reason: {reason}")
