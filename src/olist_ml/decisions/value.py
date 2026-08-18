"""Business-loss and expected-value calculations (simulation assumptions)."""

from __future__ import annotations

from olist_ml.decisions.economics import BusinessLossConfig, PolicyEconomicsConfig
from olist_ml.decisions.schemas import (
    IMPACT_ONLY_ACTIONS,
    ActionCandidate,
    ActionEconomics,
    ActionType,
)


def business_loss_if_miss(basket_value: float, cfg: BusinessLossConfig) -> float:
    """Flat loss model for binary promise_miss (no day-severity in v1)."""
    if basket_value < 0:
        raise ValueError("basket_value must be >= 0")
    return float(cfg.fixed_miss_cost + cfg.order_value_loss_rate * basket_value)


# Back-compat alias used by a few replay helpers.
business_loss_if_long = business_loss_if_miss


def score_action(
    *,
    action: ActionEconomics,
    probability: float,
    loss_if_long: float,
    cost_override: float | None = None,
) -> ActionCandidate:
    """
    Expected value under configured simulation assumptions.

    Prevention actions:
      avoided = P(risk) * prevention * loss
      net = avoided - cost

    Notices (impact-only):
      avoided = P(risk) * loss * customer_impact_reduction
      net = avoided - cost
      (prevention is ignored / should be 0)
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    if loss_if_long < 0:
        raise ValueError("loss_if_long must be >= 0")

    cost = float(action.cost if cost_override is None else cost_override)

    if action.action == ActionType.NO_ACTION:
        return ActionCandidate(
            action=action.action,
            expected_intervention_cost=0.0,
            expected_avoided_loss=0.0,
            expected_net_value=0.0,
            formula="NO_ACTION: net=0",
        )

    if action.action in IMPACT_ONLY_ACTIONS or (
        action.risk_prevention_probability <= 0 and action.customer_impact_reduction > 0
    ):
        avoided = probability * loss_if_long * action.customer_impact_reduction
        formula = (
            "P(risk)*loss*customer_impact_reduction - cost "
            f"= {probability:.4f}*{loss_if_long:.4f}*{action.customer_impact_reduction:.4f}"
            f" - {cost:.4f}"
        )
    else:
        avoided = probability * action.risk_prevention_probability * loss_if_long
        formula = (
            "P(risk)*prevention*loss - cost "
            f"= {probability:.4f}*{action.risk_prevention_probability:.4f}*{loss_if_long:.4f}"
            f" - {cost:.4f}"
        )

    net = avoided - cost
    return ActionCandidate(
        action=action.action,
        expected_intervention_cost=cost,
        expected_avoided_loss=float(avoided),
        expected_net_value=float(net),
        formula=formula,
    )


def score_all_actions(
    *,
    probability: float,
    basket_value: float,
    config: PolicyEconomicsConfig,
    cost_overrides: dict[ActionType, float] | None = None,
) -> tuple[float, list[ActionCandidate]]:
    loss = business_loss_if_miss(basket_value, config.business_loss)
    overrides = cost_overrides or {}
    candidates = [
        score_action(
            action=econ,
            probability=probability,
            loss_if_long=loss,
            cost_override=overrides.get(econ.action),
        )
        for econ in config.actions.values()
        if econ.eligible
    ]
    candidates.sort(key=lambda c: (c.expected_net_value, c.action.value), reverse=True)
    return loss, candidates
