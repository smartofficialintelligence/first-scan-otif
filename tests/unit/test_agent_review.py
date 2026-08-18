"""Unit tests for LangGraph agent review — tool-driven, copies frozen NOC policy."""

from __future__ import annotations

import pytest

from olist_ml.agents.graph import run_agent_review
from olist_ml.decisions.schemas import ActionType


@pytest.fixture
def base_state() -> dict:
    return {
        "order_id": "agent-1",
        "prediction_id": "pred-agent-1",
        "model_version": "test",
        "promise_miss_probability": 0.9,
        "basket_value": 300.0,
        "remaining_to_promise_days": 4.0,
        "geo_distance_km": 250.0,
        "same_state": 0.0,
        "freight_value": 8.0,
        "p1_score_threshold": 0.40,
        "p2_score_threshold": 0.20,
        "run_simulation": False,
        "require_human_approval": False,
        "tool_trace": [],
    }


def test_agent_executes_policy_action(base_state: dict) -> None:
    out = run_agent_review(base_state)
    assert out["status"] == "completed"
    assert out["selected_action"] in {a.value for a in ActionType}
    assert out["selected_action"] != ActionType.NO_ACTION.value
    assert out["selected_action"] == out["policy_recommendation"]["recommended_action"]
    assert "load_context:ok" in out["tool_trace"]
    assert "does not re-select policy" in out["agent_rationale"]


def test_agent_low_risk_no_action() -> None:
    out = run_agent_review(
        {
            "order_id": "low",
            "prediction_id": "p",
            "model_version": "test",
            "promise_miss_probability": 0.05,
            "basket_value": 40.0,
            "remaining_to_promise_days": 4.0,
            "p1_score_threshold": 0.40,
            "p2_score_threshold": 0.20,
            "run_simulation": False,
            "require_human_approval": False,
            "tool_trace": [],
        }
    )
    assert out["selected_action"] == ActionType.NO_ACTION.value
    assert out["status"] == "completed"


def test_human_gate_waiting() -> None:
    out = run_agent_review(
        {
            "order_id": "wait",
            "prediction_id": "p",
            "model_version": "test",
            "promise_miss_probability": 0.85,
            "basket_value": 400.0,
            "remaining_to_promise_days": 3.0,
            "geo_distance_km": 300.0,
            "same_state": 0.0,
            "freight_value": 80.0,
            "p1_score_threshold": 0.40,
            "p2_score_threshold": 0.20,
            "run_simulation": False,
            "require_human_approval": True,
            "human_approved": None,
            "tool_trace": [],
        }
    )
    assert out["status"] == "waiting_approval"
    assert out["selected_action"] != ActionType.NO_ACTION.value


def test_human_gate_reject() -> None:
    out = run_agent_review(
        {
            "order_id": "reject",
            "prediction_id": "p",
            "model_version": "test",
            "promise_miss_probability": 0.85,
            "basket_value": 400.0,
            "remaining_to_promise_days": 3.0,
            "geo_distance_km": 300.0,
            "same_state": 0.0,
            "freight_value": 80.0,
            "p1_score_threshold": 0.40,
            "p2_score_threshold": 0.20,
            "run_simulation": False,
            "require_human_approval": True,
            "human_approved": False,
            "tool_trace": [],
        }
    )
    assert out["status"] == "rejected"
    assert out["selected_action"] == ActionType.NO_ACTION.value


def test_missing_context_fails() -> None:
    out = run_agent_review({"order_id": "x", "tool_trace": []})
    assert out["status"] == "failed"
    assert "Missing fields" in (out.get("error") or "")


def test_agent_copies_policy_even_if_ev_differs() -> None:
    from olist_ml.agents import nodes

    fake_values = [
        {
            "action": "REMAINING_LEG_UPGRADE",
            "expected_net_value": 10.0,
            "expected_intervention_cost": 25.0,
        },
        {
            "action": "AT_RISK_NOTICE",
            "expected_net_value": 9.5,
            "expected_intervention_cost": 1.0,
        },
        {
            "action": "NO_ACTION",
            "expected_net_value": 0.0,
            "expected_intervention_cost": 0.0,
        },
    ]
    state = {
        "available_actions": [{"action": a["action"]} for a in fake_values],
        "action_values": fake_values,
        "policy_recommendation": {
            "recommended_action": "REMAINING_LEG_UPGRADE",
            "policy_band": "P1",
        },
        "tool_trace": [],
    }
    chosen = nodes.node_choose_action(state)
    assert chosen["selected_action"] == "REMAINING_LEG_UPGRADE"
    assert "does not re-select policy" in chosen["agent_rationale"]
