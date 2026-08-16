"""Unit tests for in-memory monitoring metrics."""

from __future__ import annotations

from olist_ml.monitoring.metrics import MetricsRegistry, get_metrics


def test_observe_predict_and_snapshot() -> None:
    m = MetricsRegistry()
    m.observe_predict(latency_ms=10.0, risk_band="low")
    m.observe_predict(latency_ms=30.0, risk_band="high", stale=True)
    m.observe_predict(latency_ms=5.0, error=True)

    snap = m.snapshot()
    assert snap["service"]["predict_requests"] == 3
    assert snap["service"]["predict_errors"] == 1
    assert snap["service"]["predict_latency_ms"]["count"] == 3
    assert snap["service"]["predict_latency_ms"]["sum"] == 45.0
    assert snap["service"]["predict_latency_ms"]["mean"] == 15.0
    assert snap["ml"]["risk_band_counts"]["low"] == 1
    assert snap["ml"]["risk_band_counts"]["high"] == 1
    assert snap["ml"]["stale_feature_rate"] == 1
    assert snap["ml"]["prediction_mix"]["high"] == 1


def test_global_metrics_reset_isolation() -> None:
    metrics = get_metrics()
    metrics.reset()
    metrics.observe_predict(latency_ms=1.0, risk_band="medium")
    assert metrics.snapshot()["service"]["predict_requests"] == 1
    metrics.reset()
    assert metrics.snapshot()["service"]["predict_requests"] == 0
    assert metrics.snapshot()["ml"]["risk_band_counts"]["medium"] == 0
