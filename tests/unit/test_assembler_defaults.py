"""Serving-side assembler defaults — regression for the same_state dead-code bug."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

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


def test_remaining_to_promise_derived_from_handoff_and_eta() -> None:
    """NOC bands consume remaining_to_promise_days; naive vs UTC must not break the clock."""
    handoff = datetime(2018, 1, 4, 11, 0, tzinfo=UTC)
    eta = datetime(2018, 1, 8, 11, 0)  # naive
    req = _request(
        prediction_timestamp=datetime(2018, 1, 1, 10, 0, tzinfo=UTC),
        handoff_timestamp=handoff,
        order_estimated_delivery_date=eta,
        shipping_limit_date=datetime(2018, 1, 3, 11, 0, tzinfo=UTC),
    )
    frame = frame_from_requests([req])
    assert float(frame.iloc[0]["remaining_to_promise_days"]) == pytest.approx(4.0)
    assert float(frame.iloc[0]["handling_days"]) == pytest.approx(3.0 + 1.0 / 24.0)
    assert float(frame.iloc[0]["limit_miss"]) == 1.0


def test_handling_days_floored_when_handoff_precedes_purchase() -> None:
    """Clock skew must not produce a large negative handling clock for NOC bands."""
    req = _request(
        prediction_timestamp=datetime(2018, 1, 5, 12, 0, tzinfo=UTC),
        handoff_timestamp=datetime(2018, 1, 1, 12, 0, tzinfo=UTC),
    )
    frame = frame_from_requests([req])
    assert float(frame.iloc[0]["handling_days"]) == pytest.approx(-1.0)


def test_handling_frac_zero_horizon_is_zero() -> None:
    req = _request(handling_days=2.0, estimated_delivery_horizon_days=0.0)
    frame = frame_from_requests([req])
    assert float(frame.iloc[0]["handling_frac_of_promise"]) == 0.0


def test_remaining_to_promise_falls_back_to_horizon_minus_handling() -> None:
    req = _request(
        remaining_to_promise_days=None,
        handling_days=2.0,
        estimated_delivery_horizon_days=10.0,
    )
    frame = frame_from_requests([req])
    assert float(frame.iloc[0]["remaining_to_promise_days"]) == pytest.approx(8.0)
    assert float(frame.iloc[0]["handling_frac_of_promise"]) == pytest.approx(0.2)
