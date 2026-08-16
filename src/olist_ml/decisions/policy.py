"""Deterministic expected-value decision policy."""

from __future__ import annotations

from olist_ml.decisions.economics import PolicyEconomicsConfig
from olist_ml.decisions.schemas import ActionCandidate, ActionType
from olist_ml.decisions.value import score_all_actions


def select_recommended_action(candidates: list[ActionCandidate]) -> ActionCandidate:
    """
    Choose argmax(expected_net_value) among candidates with net > 0.
    Otherwise NO_ACTION.
    """
    positive = [c for c in candidates if c.expected_net_value > 0]
    if not positive:
        for c in candidates:
            if c.action == ActionType.NO_ACTION:
                return c
        return ActionCandidate(
            action=ActionType.NO_ACTION,
            expected_intervention_cost=0.0,
            expected_avoided_loss=0.0,
            expected_net_value=0.0,
            formula="NO_ACTION: no positive-EV alternative",
        )
    return max(positive, key=lambda c: (c.expected_net_value, c.action.value))


def run_expected_value_policy(
    *,
    probability: float,
    basket_value: float,
    config: PolicyEconomicsConfig,
) -> tuple[float, ActionCandidate, list[ActionCandidate]]:
    loss, candidates = score_all_actions(
        probability=probability,
        basket_value=basket_value,
        config=config,
    )
    recommended = select_recommended_action(candidates)
    return loss, recommended, candidates
