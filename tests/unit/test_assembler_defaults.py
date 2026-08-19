"""Serving-side assembler defaults — regression for the same_state dead-code bug."""

from __future__ import annotations

from datetime import UTC, datetime

from olist_ml.features.assembler import frame_from_requests, noc_context_from_request
from olist_ml.schemas import PredictRequest


def _request(**overrides) -> PredictRequest:
    base = {
        "order_id": "o1",
        "seller_id": "s1",
        "purchase_timestamp": datetime(2026, 1, 5, 12, 0, tzinfo=UTC),
        "item_count": 1,
        "basket_value": 100.0,
        "freight_value": 12.0,
        "estimated_delivery_horizon_days": 10.0,
    }
    base.update(overrides)
    return PredictRequest(**base)


def test_same_state_derived_when_omitted_and_states_match() -> None:
    req = _request(customer_state="SP", seller_state_primary="SP")
    frame = frame_from_requests([req])
    assert float(frame.iloc[0]["same_state"]) == 1.0


def test_same_state_derived_when_omitted_and_states_differ() -> None:
    req = _request(customer_state="SP", seller_state_primary="BA")
    frame = frame_from_requests([req])
    assert float(frame.iloc[0]["same_state"]) == 0.0


def test_same_state_unknown_states_stay_interstate() -> None:
    # Matches training: unknown == unknown does not count as same-state.
    req = _request()
    frame = frame_from_requests([req])
    assert float(frame.iloc[0]["same_state"]) == 0.0


def test_same_state_caller_value_wins() -> None:
    req = _request(customer_state="SP", seller_state_primary="SP", same_state=0.0)
    frame = frame_from_requests([req])
    assert float(frame.iloc[0]["same_state"]) == 0.0


def test_noc_context_sees_derived_same_state() -> None:
    # Policy upgrade eligibility consumes the same derivation.
    ctx = noc_context_from_request(_request(customer_state="SP", seller_state_primary="SP"))
    assert ctx["same_state"] == 1.0
