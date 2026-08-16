"""Unit tests for LangGraph agent review (D8/D10) — tool-driven, no LLM key."""

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
        "long_delivery_probability": 0.9,
        "basket_value": 300.0,
        "run_simulation": False,
        "require_human_approval": False,
        "tool_trace": [],
    }


def test_agent_selects_positive_ev_action(base_state: dict) -> None:
    out = run_agent_review(base_state)
    assert out["status"] == "completed"
    assert out["selected_action"] in {a.value for a in ActionType}
    assert out["selected_action"] != ActionType.NO_ACTION.value
    assert "load_context:ok" in out["tool_trace"]
    assert out["policy_recommendation"]["recommended_action"]


def test_agent_low_risk_no_action() -> None:
    out = run_agent_review(
        {
            "order_id": "low",
            "prediction_id": "p",
            "model_version": "test",
            "long_delivery_probability": 0.05,
            "basket_value": 40.0,
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
            "long_delivery_probability": 0.85,
            "basket_value": 400.0,
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
            "long_delivery_probability": 0.85,
            "basket_value": 400.0,
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


def test_near_tie_prefers_lower_cost() -> None:
    """When top EV values are within $1, agent prefers cheaper action."""
    from olist_ml.agents import nodes

    fake_values = [
        {
            "action": "EXPEDITE",
            "expected_net_value": 10.0,
            "expected_intervention_cost": 25.0,
            "expected_benefit": 35.0,
        },
        {
            "action": "SELLER_ESCALATION",
            "expected_net_value": 9.5,
            "expected_intervention_cost": 5.0,
            "expected_benefit": 14.5,
        },
        {
            "action": "NO_ACTION",
            "expected_net_value": 0.0,
            "expected_intervention_cost": 0.0,
            "expected_benefit": 0.0,
        },
    ]
    state = {
        "available_actions": [{"action": a["action"]} for a in fake_values],
        "action_values": fake_values,
        "policy_recommendation": {"recommended_action": "EXPEDITE"},
        "tool_trace": [],
    }
    chosen = nodes.node_choose_action(state)
    assert chosen["selected_action"] == "SELLER_ESCALATION"
    assert "lower-cost" in chosen["agent_rationale"]
