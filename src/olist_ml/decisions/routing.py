"""Deterministic agent-review routing flags (no LLM)."""

from __future__ import annotations

from olist_ml.decisions.economics import RoutingConfig
from olist_ml.decisions.schemas import ActionCandidate, ActionType


def requires_agent_review(
    *,
    recommended: ActionCandidate,
    alternatives: list[ActionCandidate] | None = None,
    basket_value: float | None = None,
    routing: RoutingConfig,
) -> bool:
    """
    Flag exception / notice / upgrade cases for agent execution of the frozen policy.

    Does not choose the action — only sets DecisionResult.requires_agent_review.
    """
    if not routing.enable_agent_review_flags:
        return False
    return recommended.action != ActionType.NO_ACTION
