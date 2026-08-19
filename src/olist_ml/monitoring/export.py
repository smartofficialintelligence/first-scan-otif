"""Export a local monitoring snapshot (M8: dashboards or exported metrics)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from olist_ml.monitoring.delayed_eval import DEFAULT_OUT as DELAYED_OUT
from olist_ml.monitoring.drift import DEFAULT_ALARM
from olist_ml.monitoring.h5 import read_json
from olist_ml.monitoring.logs import read_jsonl
from olist_ml.monitoring.metrics import get_metrics

DEFAULT_LOG = Path("artifacts/prediction_logs.jsonl")
DEFAULT_OUT = Path("artifacts/monitoring_dashboard.json")


def export_monitoring_snapshot(
    *,
    log_path: Path = DEFAULT_LOG,
    alarm_path: Path = DEFAULT_ALARM,
    delayed_path: Path = DELAYED_OUT,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    rows = read_jsonl(log_path)
    n = len(rows)
    errors = sum(1 for r in rows if (r.get("http_status") or 0) >= 400 or r.get("error_class"))
    lat = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]
    high = sum(1 for r in rows if r.get("risk_band") == "high")
    released = sum(1 for r in rows if r.get("label_released"))
    stale = sum(1 for r in rows if r.get("stale_features"))
    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "title": "Olist promise-miss serving + ML signals",
        "service": {
            "volume": n,
            "error_rate": (errors / n) if n else 0.0,
            "mean_latency_ms": (sum(lat) / len(lat)) if lat else None,
        },
        "ml": {
            "high_band_rate": (high / n) if n else 0.0,
            "stale_feature_count": stale,
            "n_released_labels": released,
        },
        "in_process_metrics": get_metrics().snapshot(),
        "drift_alarm": read_json(alarm_path),
        "delayed_eval": read_json(delayed_path),
        "note": (
            "Local exported metrics (M8). GCP Cloud Monitoring dashboard is Terraform "
            "module terraform/modules/monitoring behind enable_monitoring (H7 apply)."
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    return snapshot
