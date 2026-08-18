"""Seeded counterfactual intervention simulation (assumptions, not causal)."""

from __future__ import annotations

import hashlib

import numpy as np

from olist_ml.decisions.economics import BusinessLossConfig
from olist_ml.decisions.schemas import IMPACT_ONLY_ACTIONS, ActionEconomics, ActionType
from olist_ml.decisions.value import business_loss_if_miss


def derive_seed(*parts: str, base_seed: int = 42) -> int:
    """Stable seed from lineage ids so replay is reproducible."""
    material = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    return (int(digest[:8], 16) ^ int(base_seed)) & 0xFFFFFFFF


def simulate_intervention(
    *,
    action: ActionEconomics,
    observed_promise_miss: bool,
    basket_value: float,
    loss_cfg: BusinessLossConfig,
    seed: int,
    cost_override: float | None = None,
) -> dict[str, float | bool | None]:
    """
    Apply configured Bernoulli prevention / impact reduction.

    Never mutates historical truth — returns parallel simulated fields.
    """
    rng = np.random.default_rng(seed)
    loss = business_loss_if_miss(basket_value, loss_cfg)
    cost = float(action.cost if cost_override is None else cost_override)

    if action.action == ActionType.NO_ACTION:
        return {
            "intervention_success": None,
            "simulated_promise_miss": bool(observed_promise_miss),
            "simulated_impact_loss_reduction": 0.0,
            "simulated_cost": 0.0,
            "simulated_gross_avoided_loss": 0.0,
            "simulated_net_value": 0.0,
            "business_loss_if_miss": loss,
        }

    # Impact-only: lateness unchanged; reduce realized customer-impact loss.
    if action.action in IMPACT_ONLY_ACTIONS or (
        action.risk_prevention_probability <= 0 and action.customer_impact_reduction > 0
    ):
        impact = float(action.customer_impact_reduction)
        avoided = (loss * impact) if observed_promise_miss else 0.0
        return {
            "intervention_success": None,
            "simulated_promise_miss": bool(observed_promise_miss),
            "simulated_impact_loss_reduction": avoided,
            "simulated_cost": cost,
            "simulated_gross_avoided_loss": avoided,
            "simulated_net_value": avoided - cost,
            "business_loss_if_miss": loss,
        }

    success = False
    simulated_miss = bool(observed_promise_miss)
    if observed_promise_miss and action.risk_prevention_probability > 0:
        success = bool(rng.random() < action.risk_prevention_probability)
        if success:
            simulated_miss = False
    avoided = loss if (observed_promise_miss and success) else 0.0
    return {
        "intervention_success": success if observed_promise_miss else None,
        "simulated_promise_miss": simulated_miss,
        "simulated_impact_loss_reduction": 0.0,
        "simulated_cost": cost,
        "simulated_gross_avoided_loss": avoided,
        "simulated_net_value": avoided - cost,
        "business_loss_if_miss": loss,
    }
