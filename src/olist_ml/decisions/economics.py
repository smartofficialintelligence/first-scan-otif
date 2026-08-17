"""Load versioned policy / economics simulation assumptions."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from olist_ml.decisions.schemas import ActionEconomics, ActionType, PolicyVersion

DEFAULT_CONFIG_PATH = Path("config/policy_economics.yaml")

EconomicsGateStatus = Literal["pending_approval", "approved", "rejected"]
GateItemStatus = Literal["pending", "approved", "rejected"]


class BusinessLossConfig(BaseModel):
    fixed_long_delivery_cost: float = Field(ge=0, default=10.0)
    order_value_loss_rate: float = Field(ge=0, default=0.10)


class RoutingConfig(BaseModel):
    high_value_order_threshold: float = Field(ge=0, default=250.0)
    top_actions_ev_margin: float = Field(ge=0, default=1.0)
    enable_agent_review_flags: bool = True
    require_human_approval_for_agent_review: bool = True
    real_external_execution_enabled: bool = False


class EconomicsGateConfig(BaseModel):
    """H9/H10 approval state for simulation economics (not causal claims)."""

    status: EconomicsGateStatus = "pending_approval"
    h9_business_loss: GateItemStatus = "pending"
    h10_intervention_effectiveness: GateItemStatus = "pending"
    approved_by: str | None = None
    approved_at: str | None = None
    notes: str = ""
    # Even when H9/H10 simulation defaults are approved, causal ROI stays off
    # unless an explicit evidence-backed flag is set later.
    allow_causal_roi_claims: bool = False

    @property
    def is_approved(self) -> bool:
        return (
            self.status == "approved"
            and self.h9_business_loss == "approved"
            and self.h10_intervention_effectiveness == "approved"
        )

    @property
    def causal_roi_claim_allowed(self) -> bool:
        return self.is_approved and self.allow_causal_roi_claims

    @property
    def simulation_claims_allowed(self) -> bool:
        """May discuss simulated EV / replay under versioned assumptions."""
        return self.is_approved


class PolicyEconomicsConfig(BaseModel):
    policy_version: str
    policy_config_version: str
    assumptions_disclaimer: str
    business_loss: BusinessLossConfig
    actions: dict[ActionType, ActionEconomics]
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    economics_gate: EconomicsGateConfig = Field(default_factory=EconomicsGateConfig)

    def policy_version_info(self, git_sha: str | None = None) -> PolicyVersion:
        return PolicyVersion(
            policy_version=self.policy_version,
            policy_config_version=self.policy_config_version,
            git_sha=git_sha,
            assumptions_disclaimer=self.assumptions_disclaimer,
        )


def _parse_actions(raw: dict[str, Any]) -> dict[ActionType, ActionEconomics]:
    out: dict[ActionType, ActionEconomics] = {}
    for key, vals in raw.items():
        action = ActionType(key)
        out[action] = ActionEconomics(
            action=action,
            cost=float(vals.get("cost", 0.0)),
            risk_prevention_probability=float(vals.get("risk_prevention_probability", 0.0)),
            customer_impact_reduction=float(vals.get("customer_impact_reduction", 0.0)),
            eligible=bool(vals.get("eligible", True)),
        )
    # Ensure NO_ACTION always present.
    if ActionType.NO_ACTION not in out:
        out[ActionType.NO_ACTION] = ActionEconomics(
            action=ActionType.NO_ACTION,
            cost=0.0,
            risk_prevention_probability=0.0,
            customer_impact_reduction=0.0,
            eligible=True,
        )
    return out


def load_policy_economics(path: Path | str | None = None) -> PolicyEconomicsConfig:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Policy economics config not found: {cfg_path}")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid policy config (expected mapping): {cfg_path}")
    actions = _parse_actions(raw.get("actions") or {})
    gate_raw = raw.get("economics_gate") or {}
    return PolicyEconomicsConfig(
        policy_version=str(raw["policy_version"]),
        policy_config_version=str(raw["policy_config_version"]),
        assumptions_disclaimer=str(raw.get("assumptions_disclaimer") or "").strip(),
        business_loss=BusinessLossConfig(**(raw.get("business_loss") or {})),
        actions=actions,
        routing=RoutingConfig(**(raw.get("routing") or {})),
        economics_gate=EconomicsGateConfig(**gate_raw),
    )


@lru_cache(maxsize=4)
def get_policy_economics(path: str | None = None) -> PolicyEconomicsConfig:
    return load_policy_economics(path)


def clear_policy_cache() -> None:
    get_policy_economics.cache_clear()
