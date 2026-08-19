"""Ops-contract tests: feature PSI drift, delayed labels, H5 retrain gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from olist_ml.features.contracts import ONLINE_SELLER_FEATURES
from olist_ml.monitoring.delayed_eval import evaluate_delayed
from olist_ml.monitoring.drift import evaluate_drift, run_drift_check
from olist_ml.monitoring.h5 import assert_retrain_allowed, write_h5_approval
from olist_ml.monitoring.labels import release_labels
from olist_ml.monitoring.logs import (
    DRIFT_FEATURE_COLUMNS,
    log_completeness,
    released_rows,
    window_for_scenario,
)
from olist_ml.monitoring.psi import high_band_relative_shift, population_stability_index
from olist_ml.monitoring.scenarios import apply_drift_scenario


def _frame(n: int = 80, *, geo: float = 100.0, late: float = 0.2) -> pd.DataFrame:
    data: dict[str, list[float]] = {col: [late] * n for col in ONLINE_SELLER_FEATURES}
    data["geo_distance_km"] = [geo] * n
    return pd.DataFrame(data)


def _logs_from_frame(frame: pd.DataFrame, window: str, *, high: bool = False) -> list[dict]:
    rows = []
    for rec in frame.to_dict(orient="records"):
        row = {
            "window": window,
            "risk_band": "high" if high else "low",
            "proba": 0.9 if high else 0.1,
            **{col: rec.get(col) for col in DRIFT_FEATURE_COLUMNS},
        }
        rows.append(row)
    return rows


def test_window_for_named_scenarios() -> None:
    assert window_for_scenario("baseline") == "baseline"
    assert window_for_scenario("bad_canary") == "baseline"
    assert window_for_scenario("drift_geo") == "recent"
    assert window_for_scenario("drift_seller_late") == "recent"


def test_drift_geo_scenario_trips_psi_alarm() -> None:
    baseline = _frame()
    recent = apply_drift_scenario(baseline, "drift_geo", seed=42)
    assert (recent["geo_distance_km"] > baseline["geo_distance_km"]).sum() >= 1
    result = evaluate_drift(_logs_from_frame(baseline, "baseline") + _logs_from_frame(recent, "recent"))
    assert result["feature_psi"]["geo_distance_km"] > 0.2
    assert "geo_distance_km" in result["alarming_features"]
    assert result["alarm"] is True
    assert result["auto_promote"] is False


def test_drift_seller_late_scenario_trips_psi_alarm() -> None:
    """Bimodal seller rates + full-population late-rate shift exceed PSI 0.2."""
    n = 100
    late = [0.0 if i < n // 2 else 0.15 for i in range(n)]
    baseline = pd.DataFrame(
        {
            **{col: list(late) for col in ONLINE_SELLER_FEATURES},
            "geo_distance_km": [50.0] * n,
        }
    )
    recent = apply_drift_scenario(baseline, "drift_seller_late", seed=42, fraction=1.0)
    shifted = [c for c in ONLINE_SELLER_FEATURES if "late_rate" in c]
    assert any((recent[c] != baseline[c]).any() for c in shifted)
    result = evaluate_drift(_logs_from_frame(baseline, "baseline") + _logs_from_frame(recent, "recent"))
    late_psi = [result["feature_psi"].get(c, 0.0) for c in shifted]
    assert max(late_psi) > 0.2
    assert result["feature_alarm"] is True
    assert result["alarm"] is True


def test_high_band_mix_shift_trips_prediction_drift() -> None:
    baseline = _logs_from_frame(_frame(40), "baseline", high=False)
    recent = _logs_from_frame(_frame(40), "recent", high=True)
    result = evaluate_drift(baseline + recent)
    assert result["prediction_mix_alarm"] is True
    assert result["high_band_relative_shift"] > 0.20
    assert result["alarm"] is True


def test_high_band_relative_shift_formula() -> None:
    assert high_band_relative_shift(0.10, 0.13) == pytest.approx(0.30)
    assert high_band_relative_shift(0.10, 0.10) == 0.0


def test_empty_logs_do_not_alarm(tmp_path: Path) -> None:
    log_path = tmp_path / "empty.jsonl"
    log_path.write_text("")
    alarm = tmp_path / "alarm.json"
    result = run_drift_check(log_path=log_path, alarm_path=alarm)
    assert result["alarm"] is False
    assert alarm.exists()


def test_psi_identical_samples_near_zero() -> None:
    import numpy as np

    x = np.linspace(0.1, 0.9, 50)
    assert population_stability_index(x, x) < 0.05


def test_run_drift_check_uses_separate_baseline_log(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.jsonl"
    recent = tmp_path / "recent.jsonl"
    alarm = tmp_path / "alarm.json"
    b_rows = _logs_from_frame(_frame(40, geo=50.0), "baseline")
    r_rows = _logs_from_frame(_frame(40, geo=400.0), "recent")
    baseline.write_text("\n".join(json.dumps(r) for r in b_rows) + "\n")
    recent.write_text("\n".join(json.dumps(r) for r in r_rows) + "\n")
    result = run_drift_check(log_path=recent, baseline_log_path=baseline, alarm_path=alarm)
    assert result["feature_psi"]["geo_distance_km"] > 0.2
    assert result["alarm"] is True
    same = run_drift_check(log_path=recent, alarm_path=alarm)
    assert same["alarm"] is False


def test_evaluate_delayed_loads_offline_pr_auc_from_meta(tmp_path: Path) -> None:
    from olist_ml.monitoring.delayed_eval import run_evaluate_delayed

    meta = tmp_path / "model_meta.json"
    meta.write_text(json.dumps({"metrics": {"test_pr_auc": 0.99}}))
    log_path = tmp_path / "logs.jsonl"
    anti = [
        {"proba": 0.1, "label_promise_miss": 1, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.2, "label_promise_miss": 1, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.8, "label_promise_miss": 0, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.9, "label_promise_miss": 0, "label_released": True, "traffic_bucket": "champion"},
    ]
    log_path.write_text("\n".join(json.dumps(r) for r in anti) + "\n")
    report = run_evaluate_delayed(
        log_path=log_path,
        out_path=tmp_path / "out.json",
        meta_path=meta,
    )
    assert report["baseline_pr_auc"] == pytest.approx(0.99)
    assert report["champion_pr_auc"] == pytest.approx(0.99)
    assert report["quality_alarm"] is True


def test_unreleased_labels_are_ignored_until_release() -> None:
    pred_ts = datetime(2018, 1, 1, tzinfo=UTC)
    rows = [
        {
            "proba": 0.9,
            "label_promise_miss": 1,
            "traffic_bucket": "champion",
            "label_released": False,
            "label_release_at": (pred_ts + timedelta(days=7)).isoformat(),
        },
        {
            "proba": 0.1,
            "label_promise_miss": 0,
            "traffic_bucket": "champion",
            "label_released": False,
            "label_release_at": (pred_ts + timedelta(days=7)).isoformat(),
        },
    ]
    assert released_rows(rows) == []
    report = evaluate_delayed(rows, champion_pr_auc=0.30)
    assert report["n_released"] == 0
    assert report["canary_quality_ok"] is False
    assert report["canary_delayed_label_gate"] == "insufficient_released_labels"

    released, n = release_labels(rows, virtual_now=pred_ts + timedelta(days=8))
    assert n == 2
    assert all(r["label_released"] for r in released)
    after = evaluate_delayed(released, champion_pr_auc=0.30)
    assert after["n_released"] == 2
    assert after["pr_auc_released"] is not None


def test_release_before_delay_keeps_labels_held() -> None:
    pred_ts = datetime(2018, 1, 1, tzinfo=UTC)
    rows = [
        {
            "proba": 0.8,
            "label_promise_miss": 1,
            "label_released": False,
            "label_release_at": (pred_ts + timedelta(days=7)).isoformat(),
        }
    ]
    updated, n = release_labels(rows, virtual_now=pred_ts + timedelta(days=3))
    assert n == 0
    assert updated[0]["label_released"] is False


def test_quality_alarm_on_pr_auc_drop() -> None:
    # Perfect ranking on a 4-row mix; baseline 0.99 → drop > 0.03.
    anti = [
        {"proba": 0.1, "label_promise_miss": 1, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.2, "label_promise_miss": 1, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.8, "label_promise_miss": 0, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.9, "label_promise_miss": 0, "label_released": True, "traffic_bucket": "champion"},
    ]
    report = evaluate_delayed(anti, baseline_pr_auc=0.99)
    assert report["quality_alarm"] is True
    assert report["pr_auc_released"] is not None
    assert 0.99 - report["pr_auc_released"] > 0.03


def test_canary_delayed_pr_auc_slack() -> None:
    champion = [
        {"proba": 0.9, "label_promise_miss": 1, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.8, "label_promise_miss": 1, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.2, "label_promise_miss": 0, "label_released": True, "traffic_bucket": "champion"},
        {"proba": 0.1, "label_promise_miss": 0, "label_released": True, "traffic_bucket": "champion"},
    ]
    challenger = [
        {"proba": 0.1, "label_promise_miss": 1, "label_released": True, "traffic_bucket": "challenger"},
        {"proba": 0.2, "label_promise_miss": 1, "label_released": True, "traffic_bucket": "challenger"},
        {"proba": 0.8, "label_promise_miss": 0, "label_released": True, "traffic_bucket": "challenger"},
        {"proba": 0.9, "label_promise_miss": 0, "label_released": True, "traffic_bucket": "challenger"},
    ]
    report = evaluate_delayed(champion + challenger)
    assert report["canary_delayed_label_gate"] == "fail"
    assert report["canary_quality_ok"] is False


def test_h5_required_before_retrain(tmp_path: Path) -> None:
    h5 = tmp_path / "h5.json"
    alarm = tmp_path / "alarm.json"
    alarm.write_text('{"alarm": true}')
    with pytest.raises(PermissionError, match="H5"):
        assert_retrain_allowed(reason="drift", h5_path=h5, alarm_path=alarm)

    write_h5_approval(approved=True, approved_by="test", reason="drift", path=h5)
    alarm.write_text('{"alarm": false}')
    with pytest.raises(PermissionError, match="drift"):
        assert_retrain_allowed(reason="drift", h5_path=h5, alarm_path=alarm)

    alarm.write_text('{"alarm": true}')
    assert_retrain_allowed(reason="drift", h5_path=h5, alarm_path=alarm)
    assert_retrain_allowed(reason="monthly", h5_path=h5, alarm_path=alarm)

    write_h5_approval(approved=False, approved_by="test", reason="monthly", path=h5)
    with pytest.raises(PermissionError, match="H5"):
        assert_retrain_allowed(reason="monthly", h5_path=h5, alarm_path=alarm)


def test_log_completeness_flags_missing_features() -> None:
    record = {
        "event_id": "x",
        "order_id": "o",
        "snapshot_id": "s",
        "scenario": "baseline",
        "request_ts": "t",
        "model_version": "v",
        "promise_miss_probability": 0.1,
        "risk_band": "low",
        "latency_ms": 1.0,
        "http_status": 200,
        "feature_freshness_ts": None,
        "feast_lookup_ms": 0.0,
        "error_class": None,
        "label_release_at": "t",
        "label_released": False,
        "geo_distance_km": 1.0,
    }
    comp = log_completeness(record)
    assert comp["log_schema_complete"] is False
    assert "seller_late_rate_30d" in comp["missing_feature_columns"]
    record["seller_late_rate_7d"] = 0.1
    record["seller_late_rate_30d"] = 0.1
    record["seller_late_rate_90d"] = 0.1
    record["seller_order_count_7d"] = 1
    record["seller_order_count_30d"] = 1
    record["seller_order_count_90d"] = 1
    comp = log_completeness(record)
    assert comp["log_schema_complete"] is True
    assert comp["features_complete"] is True
