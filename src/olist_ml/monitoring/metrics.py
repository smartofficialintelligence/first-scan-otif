"""In-memory service + ML metrics for local/demo scraping via GET /v1/metrics."""

from __future__ import annotations

from threading import Lock
from typing import Any


class MetricsRegistry:
    """Process-local counters and latency histogram summaries (sum/count)."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.predict_requests = 0
            self.predict_errors = 0
            self.predict_latency_ms_sum = 0.0
            self.predict_latency_ms_count = 0
            self.risk_band_counts: dict[str, int] = {"low": 0, "medium": 0, "high": 0}
            self.stale_feature_rate = 0
            self.decision_requests = 0
            self.agent_reviews = 0
            self.agent_waiting_approval = 0
            self.agent_completed = 0
            self.action_counts: dict[str, int] = {}
            self.intervention_spend = 0.0
            self.simulated_net_value = 0.0

    def observe_predict(
        self,
        *,
        latency_ms: float,
        risk_band: str | None = None,
        error: bool = False,
        stale: bool = False,
    ) -> None:
        """Record one predict (or explain→predict) observation."""
        with self._lock:
            self.predict_requests += 1
            self.predict_latency_ms_sum += float(latency_ms)
            self.predict_latency_ms_count += 1
            if error:
                self.predict_errors += 1
            if risk_band is not None:
                key = str(risk_band)
                self.risk_band_counts[key] = self.risk_band_counts.get(key, 0) + 1
            if stale:
                self.stale_feature_rate += 1

    def observe_decision(self, *, recommended_action: str | None = None) -> None:
        with self._lock:
            self.decision_requests += 1
            if recommended_action:
                self.action_counts[recommended_action] = (
                    self.action_counts.get(recommended_action, 0) + 1
                )

    def observe_agent_review(
        self,
        *,
        status: str,
        action: str | None = None,
        spend: float = 0.0,
        net: float = 0.0,
    ) -> None:
        with self._lock:
            self.agent_reviews += 1
            if status == "waiting_approval":
                self.agent_waiting_approval += 1
            if status == "completed":
                self.agent_completed += 1
            if action:
                self.action_counts[action] = self.action_counts.get(action, 0) + 1
            self.intervention_spend += float(spend)
            self.simulated_net_value += float(net)

    def snapshot(self) -> dict[str, Any]:
        """JSON-serializable metrics snapshot (service + ML + decision signals)."""
        with self._lock:
            count = self.predict_latency_ms_count
            mean_ms = (self.predict_latency_ms_sum / count) if count else 0.0
            return {
                "service": {
                    "predict_requests": self.predict_requests,
                    "predict_errors": self.predict_errors,
                    "predict_latency_ms": {
                        "sum": self.predict_latency_ms_sum,
                        "count": count,
                        "mean": mean_ms,
                    },
                },
                "ml": {
                    "risk_band_counts": dict(self.risk_band_counts),
                    "stale_feature_rate": self.stale_feature_rate,
                    "prediction_mix": dict(self.risk_band_counts),
                },
                "decision": {
                    "decision_requests": self.decision_requests,
                    "agent_reviews": self.agent_reviews,
                    "agent_waiting_approval": self.agent_waiting_approval,
                    "agent_completed": self.agent_completed,
                    "action_distribution": dict(self.action_counts),
                    "intervention_spend_simulated": self.intervention_spend,
                    "net_value_simulated": self.simulated_net_value,
                },
            }


_METRICS = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    return _METRICS
