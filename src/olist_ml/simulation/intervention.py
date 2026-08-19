"""Seeded counterfactual intervention simulation (assumptions, not causal)."""

from __future__ import annotations

import hashlib

import numpy as np

from olist_ml.decisions.economics import BusinessLossConfig
from olist_ml.decisions.schemas import IMPACT_ONLY_ACTIONS, ActionEconomics, ActionType
from olist_ml.decisions.value import business_loss_if_miss

# Fallback when replay does not pass observed (delivery − EDD)+.
# Matches docs/limitations-assumptions-proxies.md (median overrun on misses).
DEFAULT_MISS_OVERRUN_DAYS = 6.0


def resolve_observed_days_late(
    observed_promise_miss: bool,
    observed_days_late: float | None,
    *,
    median_miss_overrun_days: float = DEFAULT_MISS_OVERRUN_DAYS,
) -> float:
    """Days after promise. Caller value wins; else median-on-miss or 0."""
    if observed_days_late is not None:
        return max(0.0, float(observed_days_late))
    return float(median_miss_overrun_days) if observed_promise_miss else 0.0


def _delay_fields(
    *,
    observed_days_late: float,
    prevent_lateness: bool,
) -> dict[str, float]:
    simulated = 0.0 if prevent_lateness else observed_days_late
    return {
        "observed_days_late": observed_days_late,
        "simulated_days_late": simulated,
        "simulated_delay_days_avoided": max(0.0, observed_days_late - simulated),
    }


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
    observed_days_late: float | None = None,
) -> dict[str, float | bool | None]:
    """
    Apply configured Bernoulli prevention / impact reduction.

    Never mutates historical truth — returns parallel simulated fields.
    Notices do not change days late. Upgrade success sets simulated days late to 0
    and credits observed overrun as delay avoided (replay diagnostic, not a new EDD).
    """
    rng = np.random.default_rng(seed)
    loss = business_loss_if_miss(basket_value, loss_cfg)
    cost = float(action.cost if cost_override is None else cost_override)
    days_obs = resolve_observed_days_late(
        observed_promise_miss,
        observed_days_late,
        median_miss_overrun_days=float(loss_cfg.median_miss_overrun_days),
    )

    if action.action == ActionType.NO_ACTION:
        return {
            "intervention_success": None,
            "simulated_promise_miss": bool(observed_promise_miss),
            "simulated_impact_loss_reduction": 0.0,
            "simulated_cost": 0.0,
            "simulated_gross_avoided_loss": 0.0,
            "simulated_net_value": 0.0,
            "business_loss_if_miss": loss,
            **_delay_fields(observed_days_late=days_obs, prevent_lateness=False),
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
            **_delay_fields(observed_days_late=days_obs, prevent_lateness=False),
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
        **_delay_fields(observed_days_late=days_obs, prevent_lateness=success),
    }
