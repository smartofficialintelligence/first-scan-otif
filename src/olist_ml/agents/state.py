"""LangGraph agent review state."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentReviewState(TypedDict, total=False):
    # Inputs
    order_id: str
    seller_id: str
    basket_value: float
    long_delivery_probability: float
    prediction_id: str
    model_version: str
    observed_long_delivery: bool | None
    feature_payload: dict[str, Any]
    require_human_approval: bool
    human_approved: bool | None  # None=pending, True/False when resolved
    run_simulation: bool

    # Tool / intermediate
    available_actions: list[dict[str, Any]]
    action_values: list[dict[str, Any]]
    policy_recommendation: dict[str, Any]
    tool_trace: list[str]

    # Outputs
    selected_action: str
    agent_rationale: str
    decision_id: str
    policy_version: str
    action_result: dict[str, Any] | None
    status: str
    error: str | None
