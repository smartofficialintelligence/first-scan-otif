"""Deterministic NOC policy at carrier handoff (bands, not EV-argmax)."""

from __future__ import annotations

from olist_ml.decisions.economics import NocPolicyConfig, PolicyEconomicsConfig
from olist_ml.decisions.schemas import (
    ActionCandidate,
    ActionType,
    DecisionContext,
    PolicyBand,
)
from olist_ml.decisions.upgrade_cost import remaining_leg_upgrade_cost
from olist_ml.decisions.value import score_action, score_all_actions


def select_recommended_action(candidates: list[ActionCandidate]) -> ActionCandidate:
    """
    Appendix: argmax(expected_net_value) among candidates with net > 0.
    Otherwise NO_ACTION. Not used for the live NOC recommendation.
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
    cost_overrides: dict[ActionType, float] | None = None,
) -> tuple[float, ActionCandidate, list[ActionCandidate]]:
    loss, candidates = score_all_actions(
        probability=probability,
        basket_value=basket_value,
        config=config,
        cost_overrides=cost_overrides,
    )
    recommended = select_recommended_action(candidates)
    return loss, recommended, candidates


def upgrade_eligible(
    *,
    remaining_to_promise_days: float | None,
    geo_distance_km: float | None,
    same_state: float | None,
    noc: NocPolicyConfig,
) -> bool:
    if remaining_to_promise_days is None:
        return False
    if not (0.0 < float(remaining_to_promise_days) <= noc.upgrade_remaining_max_days):
        return False
    far = geo_distance_km is not None and float(geo_distance_km) >= noc.upgrade_min_geo_km
    interstate = same_state is not None and float(same_state) == 0.0
    return bool(far or interstate)


def assign_policy_band(
    *,
    probability: float,
    remaining_to_promise_days: float | None,
    p1_score_threshold: float,
    p2_score_threshold: float,
) -> PolicyBand:
    if remaining_to_promise_days is not None and float(remaining_to_promise_days) <= 0:
        return "P0"
    if probability >= p1_score_threshold:
        return "P1"
    if probability >= p2_score_threshold:
        return "P2"
    return "P3"


def action_for_band(band: PolicyBand, eligible: bool) -> ActionType:
    if band == "P0":
        return ActionType.LATE_NOTICE
    if band == "P1":
        return ActionType.REMAINING_LEG_UPGRADE if eligible else ActionType.AT_RISK_NOTICE
    if band == "P2":
        return ActionType.AT_RISK_NOTICE
    return ActionType.NO_ACTION


def apply_noc_policy(
    context: DecisionContext,
    config: PolicyEconomicsConfig,
) -> tuple[float, ActionCandidate, list[ActionCandidate], dict[str, object]]:
    """
    Deterministic P0–P3 band policy.

    Returns loss, recommended candidate, EV appendix candidates, and band metadata.
    """
    noc = config.noc_policy
    p1 = (
        context.p1_score_threshold
        if context.p1_score_threshold is not None
        else noc.default_p1_score_threshold
    )
    p2 = (
        context.p2_score_threshold
        if context.p2_score_threshold is not None
        else noc.default_p2_score_threshold
    )
    band = assign_policy_band(
        probability=context.promise_miss_probability,
        remaining_to_promise_days=context.remaining_to_promise_days,
        p1_score_threshold=p1,
        p2_score_threshold=p2,
    )
    eligible = upgrade_eligible(
        remaining_to_promise_days=context.remaining_to_promise_days,
        geo_distance_km=context.geo_distance_km,
        same_state=context.same_state,
        noc=noc,
    )
    if band != "P1":
        eligible = False
    action = action_for_band(band, eligible)

    upgrade_cost: float | None = None
    cost_overrides: dict[ActionType, float] = {}
    if action == ActionType.REMAINING_LEG_UPGRADE:
        upgrade_cost = remaining_leg_upgrade_cost(
            context.order_id,
            float(context.freight_value or 0.0),
            context.basket_value,
            config=noc.upgrade_cost,
        )
        cost_overrides[ActionType.REMAINING_LEG_UPGRADE] = upgrade_cost

    loss, candidates = score_all_actions(
        probability=context.promise_miss_probability,
        basket_value=context.basket_value,
        config=config,
        cost_overrides=cost_overrides,
    )
    recommended = next((c for c in candidates if c.action == action), None)
    if recommended is None:
        econ = config.actions[action]
        recommended = score_action(
            action=econ,
            probability=context.promise_miss_probability,
            loss_if_long=loss,
            cost_override=upgrade_cost,
        )

    meta: dict[str, object] = {
        "policy_band": band,
        "upgrade_eligible": eligible,
        "upgrade_cost": upgrade_cost,
        "remaining_to_promise_days": context.remaining_to_promise_days,
        "p1_score_threshold": p1,
        "p2_score_threshold": p2,
        "requires_human_approval": (
            action == ActionType.REMAINING_LEG_UPGRADE
            and upgrade_cost is not None
            and upgrade_cost >= noc.human_approval_upgrade_cost_min
        ),
    }
    return loss, recommended, candidates, meta
