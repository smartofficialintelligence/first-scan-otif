"""Derived clocks at first carrier scan (knowable at handoff; never uses customer delivery)."""

from __future__ import annotations

from datetime import datetime

HANDLING_DAYS_FLOOR = -1.0


def _as_aware(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        from datetime import UTC

        return ts.replace(tzinfo=UTC)
    return ts


def handling_days(prediction_ts: datetime | None, handoff_ts: datetime | None) -> float | None:
    pred = _as_aware(prediction_ts)
    handoff = _as_aware(handoff_ts)
    if pred is None or handoff is None:
        return None
    days = (handoff - pred).total_seconds() / 86400.0
    return max(HANDLING_DAYS_FLOOR, float(days))


def remaining_to_promise_days(
    handoff_ts: datetime | None, estimated_delivery: datetime | None
) -> float | None:
    handoff = _as_aware(handoff_ts)
    eta = _as_aware(estimated_delivery)
    if handoff is None or eta is None:
        return None
    return float((eta - handoff).total_seconds() / 86400.0)


def handling_frac_of_promise(handling: float | None, horizon_days: float | None) -> float:
    if handling is None or horizon_days is None:
        return 0.0
    if abs(float(horizon_days)) < 1e-6:
        return 0.0
    return float(handling) / float(horizon_days)


def limit_miss_flag(handoff_ts: datetime | None, shipping_limit: datetime | None) -> float:
    handoff = _as_aware(handoff_ts)
    limit = _as_aware(shipping_limit)
    if handoff is None or limit is None:
        return 0.0
    return 1.0 if handoff > limit else 0.0
