"""Feature PSI + prediction-mix drift vs locked gate defaults."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from olist_ml.monitoring.logs import DRIFT_FEATURE_COLUMNS, read_jsonl
from olist_ml.monitoring.psi import (
    HIGH_BAND_RELATIVE_SHIFT_THRESHOLD,
    PSI_ALARM_THRESHOLD,
    high_band_relative_shift,
    population_stability_index,
)

DEFAULT_LOG = Path("artifacts/prediction_logs.jsonl")
DEFAULT_BASELINE_LOG = Path("artifacts/prediction_logs_baseline.jsonl")
DEFAULT_ALARM = Path("artifacts/drift_alarm.json")


def _numeric(rows: list[dict[str, Any]], column: str) -> np.ndarray:
    vals = []
    for row in rows:
        v = row.get(column)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return np.asarray(vals, dtype=float)


def _high_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    high = sum(1 for r in rows if str(r.get("risk_band") or "") == "high")
    return high / len(rows)


def split_baseline_recent(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """
    Baseline vs recent windows, plus how the baseline was obtained.

    Prefer explicit ``window`` tags ("window_tags"); else first half vs second
    half in log order ("first_half_fallback"). The fallback compares a log to
    itself — a uniformly drifted log yields PSI ≈ 0 — so callers must surface
    it as inconclusive rather than "no drift".
    """
    tagged_b = [r for r in rows if r.get("window") == "baseline"]
    tagged_r = [r for r in rows if r.get("window") == "recent"]
    if tagged_b and tagged_r:
        return tagged_b, tagged_r, "window_tags"
    if len(rows) < 4:
        return rows, rows, "first_half_fallback"
    mid = len(rows) // 2
    return rows[:mid], rows[mid:], "first_half_fallback"


def evaluate_drift(
    rows: list[dict[str, Any]],
    *,
    psi_threshold: float = PSI_ALARM_THRESHOLD,
    high_band_threshold: float = HIGH_BAND_RELATIVE_SHIFT_THRESHOLD,
) -> dict[str, Any]:
    baseline, recent, baseline_source = split_baseline_recent(rows)
    feature_psi: dict[str, float] = {}
    alarming_features: list[str] = []
    for col in DRIFT_FEATURE_COLUMNS:
        b = _numeric(baseline, col)
        r = _numeric(recent, col)
        if len(b) < 2 or len(r) < 2:
            continue
        psi = population_stability_index(b, r)
        feature_psi[col] = psi
        if psi > psi_threshold:
            alarming_features.append(col)

    base_high = _high_rate(baseline)
    recent_high = _high_rate(recent)
    mix_shift = high_band_relative_shift(base_high, recent_high)
    mix_alarm = mix_shift > high_band_threshold

    feature_alarm = bool(alarming_features)
    alarmed = feature_alarm or mix_alarm
    return {
        "alarm": alarmed,
        "baseline_source": baseline_source,
        "feature_alarm": feature_alarm,
        "prediction_mix_alarm": mix_alarm,
        "psi_threshold": psi_threshold,
        "high_band_relative_threshold": high_band_threshold,
        "feature_psi": feature_psi,
        "alarming_features": alarming_features,
        "baseline_high_rate": base_high,
        "recent_high_rate": recent_high,
        "high_band_relative_shift": mix_shift,
        "n_baseline": len(baseline),
        "n_recent": len(recent),
        "deploy": False,
        "auto_promote": False,
        "human_gates": {
            "H5": "required before retrain trigger on alarm",
            "H6": "required before any promote",
        },
        "message": (
            "DRIFT_ALARM — open retrain candidate after H5"
            if alarmed
            else "ok — no drift alarm"
        ),
    }


def _tag_window(rows: list[dict[str, Any]], window: str) -> list[dict[str, Any]]:
    return [{**row, "window": window} for row in rows]


def merge_baseline_recent(
    recent_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not baseline_rows:
        return recent_rows
    return _tag_window(baseline_rows, "baseline") + _tag_window(recent_rows, "recent")


def resolve_baseline_log(explicit: Path | None = None) -> Path | None:
    """CLI/DAG share this: explicit path, else artifacts/prediction_logs_baseline.jsonl."""
    if explicit is not None:
        return explicit
    if DEFAULT_BASELINE_LOG.exists():
        return DEFAULT_BASELINE_LOG
    return None


def run_drift_check(
    *,
    log_path: Path = DEFAULT_LOG,
    baseline_log_path: Path | None = None,
    alarm_path: Path = DEFAULT_ALARM,
    psi_threshold: float = PSI_ALARM_THRESHOLD,
) -> dict[str, Any]:
    recent = read_jsonl(log_path)
    baseline_rows = read_jsonl(baseline_log_path) if baseline_log_path is not None else None
    rows = merge_baseline_recent(recent, baseline_rows)
    result = evaluate_drift(rows, psi_threshold=psi_threshold)
    if result["baseline_source"] == "first_half_fallback":
        # No trusted baseline: a uniformly drifted log self-compares to PSI ≈ 0.
        # Fail loudly instead of reporting "ok — no drift alarm".
        result["baseline_missing"] = True
        result["message"] = (
            "INCONCLUSIVE — no baseline window. Provide window-tagged rows or "
            f"a baseline log ({DEFAULT_BASELINE_LOG}); drift was NOT evaluated "
            "against a trusted baseline."
        )
    else:
        result["baseline_missing"] = False
    sources = [str(log_path) if log_path.exists() else "missing"]
    if baseline_log_path is not None:
        sources.insert(0, str(baseline_log_path))
    result.update(
        {
            "source": "+".join(sources),
            "checked_at": datetime.now(UTC).isoformat(),
        }
    )
    alarm_path.parent.mkdir(parents=True, exist_ok=True)
    alarm_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result
