"""Prediction-log IO used by replay, drift, delayed-label eval, and canary."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_LABEL_DELAY = timedelta(days=7)

DRIFT_FEATURE_COLUMNS = (
    "geo_distance_km",
    "seller_late_rate_7d",
    "seller_late_rate_30d",
    "seller_late_rate_90d",
    "seller_order_count_7d",
    "seller_order_count_30d",
    "seller_order_count_90d",
)

# simulation.md prediction-log minimum + delayed-label / PSI columns.
MIN_PREDICTION_LOG_COLUMNS = (
    "event_id",
    "order_id",
    "snapshot_id",
    "scenario",
    "request_ts",
    "model_version",
    "promise_miss_probability",
    "risk_band",
    "latency_ms",
    "http_status",
    "feature_freshness_ts",
    "feast_lookup_ms",
    "error_class",
    "label_release_at",
    "label_released",
) + DRIFT_FEATURE_COLUMNS


def window_for_scenario(scenario: str) -> str:
    name = (scenario or "baseline").strip().lower()
    if name.startswith("drift_"):
        return "recent"
    return "baseline"


def log_completeness(record: dict[str, Any]) -> dict[str, Any]:
    """Snapshot/scenario completeness vs the locked min column list."""
    missing_keys = [c for c in MIN_PREDICTION_LOG_COLUMNS if c not in record]
    missing_features = [c for c in DRIFT_FEATURE_COLUMNS if record.get(c) is None]
    return {
        "log_schema_complete": not missing_keys,
        "missing_log_columns": missing_keys,
        "features_complete": not missing_features,
        "missing_feature_columns": missing_features,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str) + "\n")


def label_release_at(
    prediction_timestamp: datetime,
    delay: timedelta = DEFAULT_LABEL_DELAY,
    *,
    outcome_timestamp: datetime | None = None,
) -> datetime:
    """When the promise-miss label is knowable.

    Prefer customer delivery (the outcome clock). Fall back to prediction_ts + delay
    only when delivery is not yet in the log.
    """
    if outcome_timestamp is not None:
        return outcome_timestamp
    return prediction_timestamp + delay


def released_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows whose delayed labels are marked released (eval/canary quality path)."""
    out = []
    for row in rows:
        if not row.get("label_released"):
            continue
        if row.get("label_promise_miss") is None:
            continue
        if row.get("proba") is None and row.get("promise_miss_probability") is None:
            continue
        out.append(row)
    return out


load_jsonl = read_jsonl
