"""Deterministic agent-review routing flags (no LLM in D1–D2)."""

from __future__ import annotations

from olist_ml.decisions.economics import RoutingConfig
from olist_ml.decisions.schemas import ActionCandidate, ActionType


def requires_agent_review(
    *,
    recommended: ActionCandidate,
    alternatives: list[ActionCandidate],
    basket_value: float,
    routing: RoutingConfig,
) -> bool:
    """
    Flag ambiguous / high-value cases for later agent review.

    Does not invoke an agent — only sets DecisionResult.requires_agent_review.
    """
    if not routing.enable_agent_review_flags:
        return False

    if recommended.action == ActionType.NO_ACTION:
        return False

    if basket_value >= routing.high_value_order_threshold:
        return True

    # Compare recommended vs next-best distinct action by EV.
    others = [c for c in alternatives if c.action != recommended.action]
    if not others:
        return False
    second = max(others, key=lambda c: c.expected_net_value)
    if second.expected_net_value <= 0:
        return False
    gap = recommended.expected_net_value - second.expected_net_value
    return gap <= routing.top_actions_ev_margin
