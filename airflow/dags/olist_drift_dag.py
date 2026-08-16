#!/usr/bin/env python3
"""
Olist drift-check DAG stub.

Computes a simple PSI or mean-shift on a numeric column from prediction logs
or fixtures; writes ``artifacts/drift_alarm.json``. Does **not** deploy.

H5 still required before any retrain; H6 before promote. No auto-promote.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

dag = None  # type: ignore[assignment]

DEFAULT_LOG = Path("artifacts/prediction_logs.jsonl")
DEFAULT_ALARM = Path("artifacts/drift_alarm.json")
PSI_THRESHOLD = 0.2


def _psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two 1-d samples."""
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    if len(expected) < 2 or len(actual) < 2:
        return 0.0
    quantiles = np.linspace(0, 1, bins + 1)
    cuts = np.unique(np.quantile(expected, quantiles))
    if len(cuts) < 3:
        # Degenerate: fall back to mean-shift normalized proxy.
        mu_e, mu_a = float(np.mean(expected)), float(np.mean(actual))
        sigma = float(np.std(expected)) or 1.0
        return abs(mu_a - mu_e) / sigma
    exp_counts, _ = np.histogram(expected, bins=cuts)
    act_counts, _ = np.histogram(actual, bins=cuts)
    exp_pct = exp_counts / max(exp_counts.sum(), 1)
    act_pct = act_counts / max(act_counts.sum(), 1)
    exp_pct = np.clip(exp_pct, 1e-6, None)
    act_pct = np.clip(act_pct, 1e-6, None)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def _load_numeric_series(
    log_path: Path,
    fixture_csv: Path,
    column: str,
) -> tuple[np.ndarray, np.ndarray, str]:
    """
    Baseline = first half of available values; recent = second half.
    Prefer prediction log ``proba`` / column; else fixture column.
    """
    values: list[float] = []
    source = "none"

    if log_path.exists():
        rows = []
        with log_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        key = column if column in (rows[0] if rows else {}) else "proba"
        for r in rows:
            v = r.get(key)
            if v is not None:
                values.append(float(v))
        source = f"prediction_logs:{key}"

    if len(values) < 4 and fixture_csv.exists():
        df = pd.read_csv(fixture_csv)
        col = column if column in df.columns else (
            "geo_distance_km" if "geo_distance_km" in df.columns else None
        )
        if col is not None:
            values = [float(x) for x in df[col].dropna().tolist()]
            source = f"fixtures:{col}"

    arr = np.asarray(values, dtype=float)
    if len(arr) < 4:
        # Synthetic stable baseline so the stub is runnable without artifacts.
        rng = np.random.default_rng(42)
        arr = rng.normal(0.3, 0.1, size=40)
        source = "synthetic"
    mid = len(arr) // 2
    return arr[:mid], arr[mid:], source


def run_drift_check(
    *,
    log_path: Path = DEFAULT_LOG,
    fixture_csv: Path = Path("artifacts/replay_holdout.csv"),
    column: str = "proba",
    alarm_path: Path = DEFAULT_ALARM,
    psi_threshold: float = PSI_THRESHOLD,
) -> dict[str, Any]:
    """Compute PSI / mean-shift; set drift alarm flag. Does not deploy."""
    baseline, recent, source = _load_numeric_series(log_path, fixture_csv, column)
    psi = _psi(baseline, recent)
    mean_shift = float(abs(np.mean(recent) - np.mean(baseline)))
    alarmed = bool(psi > psi_threshold)

    result = {
        "alarm": alarmed,
        "psi": psi,
        "psi_threshold": psi_threshold,
        "mean_shift": mean_shift,
        "column": column,
        "source": source,
        "n_baseline": int(len(baseline)),
        "n_recent": int(len(recent)),
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
        "checked_at": datetime.now(UTC).isoformat(),
    }
    alarm_path.parent.mkdir(parents=True, exist_ok=True)
    alarm_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator

    def _drift_task(**_context: Any) -> dict[str, Any]:
        return run_drift_check()

    with DAG(
        dag_id="olist_drift",
        description="Drift check stub (PSI/mean-shift); sets alarm flag; no deploy",
        start_date=datetime(2024, 1, 1),
        schedule=None,
        catchup=False,
        tags=["olist", "drift", "m10"],
    ) as dag:
        PythonOperator(
            task_id="run_drift_check",
            python_callable=_drift_task,
        )
except ImportError:
    dag = None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local drift check (no Composer)")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--fixture-csv", type=Path, default=Path("artifacts/replay_holdout.csv"))
    parser.add_argument("--column", type=str, default="proba")
    parser.add_argument("--alarm-path", type=Path, default=DEFAULT_ALARM)
    args = parser.parse_args(argv)
    result = run_drift_check(
        log_path=args.log_path,
        fixture_csv=args.fixture_csv,
        column=args.column,
        alarm_path=args.alarm_path,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
