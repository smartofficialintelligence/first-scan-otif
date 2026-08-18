"""Decision / action domain schemas (handoff NOC policy)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    NO_ACTION = "NO_ACTION"
    LATE_NOTICE = "LATE_NOTICE"
    AT_RISK_NOTICE = "AT_RISK_NOTICE"
    REMAINING_LEG_UPGRADE = "REMAINING_LEG_UPGRADE"


PolicyBand = Literal["P0", "P1", "P2", "P3"]
DecisionSource = Literal["deterministic_policy", "agent_review_pending"]
IMPACT_ONLY_ACTIONS = frozenset({ActionType.LATE_NOTICE, ActionType.AT_RISK_NOTICE})


class ActionEconomics(BaseModel):
    """Versioned simulation assumptions for one action (not causal estimates)."""

    action: ActionType
    cost: float = Field(ge=0)
    risk_prevention_probability: float = Field(ge=0, le=1)
    customer_impact_reduction: float = Field(ge=0, le=1, default=0.0)
    eligible: bool = True


class ActionCandidate(BaseModel):
    action: ActionType
    expected_intervention_cost: float
    expected_avoided_loss: float
    expected_net_value: float
    formula: str


class DecisionContext(BaseModel):
    """Inputs required to score a decision (prediction + order economics)."""

    order_id: str
    prediction_id: str
    model_version: str
    promise_miss_probability: float = Field(ge=0, le=1)
    basket_value: float = Field(ge=0)
    seller_id: str | None = None
    prediction_timestamp: datetime | None = None
    feature_version: str | None = None
    remaining_to_promise_days: float | None = None
    geo_distance_km: float | None = None
    same_state: float | None = None
    freight_value: float | None = None
    p1_score_threshold: float | None = None
    p2_score_threshold: float | None = None


class PolicyVersion(BaseModel):
    policy_version: str
    policy_config_version: str
    git_sha: str | None = None
    assumptions_disclaimer: str


class DecisionResult(BaseModel):
    decision_id: str
    prediction_id: str
    order_id: str
    promise_miss_probability: float = Field(ge=0, le=1)
    model_version: str
    policy_version: str
    policy_config_version: str
    recommended_action: ActionType
    policy_band: PolicyBand
    upgrade_eligible: bool = False
    upgrade_cost: float | None = None
    remaining_to_promise_days: float | None = None
    expected_intervention_cost: float
    expected_avoided_loss: float
    expected_net_value: float
    alternative_actions: list[ActionCandidate]
    requires_agent_review: bool
    requires_human_approval: bool = False
    decision_source: DecisionSource
    rationale: str
    decision_timestamp: datetime
    git_sha: str | None = None
    basket_value: float
    business_loss_if_miss: float
    assumptions_disclaimer: str
