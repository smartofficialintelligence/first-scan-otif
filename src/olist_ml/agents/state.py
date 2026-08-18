"""LangGraph agent review state."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentReviewState(TypedDict, total=False):
    # Inputs
    order_id: str
    seller_id: str
    basket_value: float
    promise_miss_probability: float
    remaining_to_promise_days: float | None
    geo_distance_km: float | None
    same_state: float | None
    freight_value: float | None
    p1_score_threshold: float | None
    p2_score_threshold: float | None
    prediction_id: str
    model_version: str
    observed_promise_miss: bool | None
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
