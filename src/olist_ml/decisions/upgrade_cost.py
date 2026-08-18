"""Freight-scaled remaining-leg upgrade cost (demo proxy, not a tariff)."""

from __future__ import annotations

import hashlib

import numpy as np

from olist_ml.decisions.economics import UpgradeCostConfig


def seed_from_order_id(order_id: str, *, salt: str = "upgrade-cost-v1") -> int:
    """Stable 32-bit seed from order_id (hashlib, never Python hash())."""
    digest = hashlib.sha256(f"{salt}|{order_id}".encode()).hexdigest()
    return int(digest[:8], 16)


def upgrade_multiplier(
    order_id: str,
    *,
    median: float = 0.50,
    sigma_log: float = 0.35,
) -> float:
    rng = np.random.default_rng(seed_from_order_id(order_id))
    # Lognormal median = exp(mean) when mean is log(median).
    return float(rng.lognormal(mean=float(np.log(median)), sigma=sigma_log))


def remaining_leg_upgrade_cost(
    order_id: str,
    freight_value: float,
    basket_value: float,
    *,
    config: UpgradeCostConfig | None = None,
    median_multiplier: float | None = None,
) -> float:
    """
    clip(freight * lognormal_mult, min=5, max=min(80, 0.08 * basket)).

    freight_value is a scale proxy only — not a paid express SKU.
    """
    cfg = config or UpgradeCostConfig()
    median = (
        cfg.median_freight_multiplier if median_multiplier is None else float(median_multiplier)
    )
    freight = max(float(freight_value or 0.0), 0.0)
    basket = max(float(basket_value or 0.0), 0.0)
    raw = freight * upgrade_multiplier(order_id, median=median, sigma_log=cfg.sigma_log)
    basket_cap = cfg.max_basket_frac * basket if basket > 0 else cfg.max_cost
    hi = max(cfg.min_cost, min(cfg.max_cost, basket_cap))
    return float(np.clip(raw, cfg.min_cost, hi))
