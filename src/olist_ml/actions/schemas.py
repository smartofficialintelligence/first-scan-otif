"""Action execution schemas (D3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from olist_ml.decisions.schemas import ActionType

ActionStatus = Literal["simulated", "rejected"]
ExecutionSource = Literal["deterministic_policy", "manual", "replay"]


class ActionRequest(BaseModel):
    order_id: str
    prediction_id: str
    decision_id: str
    action_type: ActionType
    model_version: str
    policy_version: str
    expected_net_value: float | None = None
    agent_run_id: str | None = None
    observed_long_delivery: bool
    basket_value: float = Field(ge=0)
    seed: int | None = None


class ActionResult(BaseModel):
    action_id: str
    order_id: str
    prediction_id: str
    decision_id: str
    action_type: ActionType
    status: ActionStatus
    simulated_cost: float
    intervention_success: bool | None
    observed_long_delivery: bool
    simulated_long_delivery: bool
    simulated_impact_loss_reduction: float = 0.0
    simulated_gross_avoided_loss: float = 0.0
    simulated_net_value: float = 0.0
    execution_source: ExecutionSource
    policy_version: str
    model_version: str
    assumptions_disclaimer: str
    timestamp: datetime
    seed_used: int
