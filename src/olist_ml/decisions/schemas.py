"""Decision / action domain schemas (D1)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    NO_ACTION = "NO_ACTION"
    EXPEDITE = "EXPEDITE"
    SELLER_ESCALATION = "SELLER_ESCALATION"
    CUSTOMER_NOTIFICATION = "CUSTOMER_NOTIFICATION"
    MANUAL_REVIEW = "MANUAL_REVIEW"


DecisionSource = Literal["deterministic_policy", "agent_review_pending"]


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
    long_delivery_probability: float = Field(ge=0, le=1)
    basket_value: float = Field(ge=0)
    seller_id: str | None = None
    prediction_timestamp: datetime | None = None
    feature_version: str | None = None


class PolicyVersion(BaseModel):
    policy_version: str
    policy_config_version: str
    git_sha: str | None = None
    assumptions_disclaimer: str


class DecisionResult(BaseModel):
    decision_id: str
    prediction_id: str
    order_id: str
    long_delivery_probability: float = Field(ge=0, le=1)
    model_version: str
    policy_version: str
    policy_config_version: str
    recommended_action: ActionType
    expected_intervention_cost: float
    expected_avoided_loss: float
    expected_net_value: float
    alternative_actions: list[ActionCandidate]
    requires_agent_review: bool
    decision_source: DecisionSource
    rationale: str
    decision_timestamp: datetime
    git_sha: str | None = None
    basket_value: float
    business_loss_if_long: float
    assumptions_disclaimer: str
