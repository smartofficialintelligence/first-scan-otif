"""Pydantic request/response and shared domain schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RiskBand = Literal["low", "medium", "high"]


class PredictRequest(BaseModel):
    order_id: str
    seller_id: str
    purchase_timestamp: datetime
    prediction_timestamp: datetime | None = None
    item_count: int = Field(ge=1)
    basket_value: float = Field(ge=0)
    freight_value: float = Field(ge=0)
    seller_count: int = Field(default=1, ge=1)
    category_count: int = Field(default=1, ge=1)
    payment_type_primary: str = "unknown"
    installment_count: int = Field(default=1, ge=1)
    estimated_delivery_horizon_days: float
    customer_state: str = "unknown"
    seller_state_primary: str = "unknown"
    geo_distance_km: float = Field(default=0.0, ge=0)

    # Request-native extras (knowable at prediction_ts).
    approval_lag_hours: float | None = Field(default=None, ge=0)
    same_state: float | None = None
    avg_product_weight_g: float | None = Field(default=None, ge=0)
    freight_to_basket_ratio: float | None = Field(default=None, ge=0)
    primary_category: str = "unknown"

    # Optional historical features when Feast online is unavailable (local mode).
    seller_order_count_7d: float | None = None
    seller_order_count_30d: float | None = None
    seller_order_count_90d: float | None = None
    seller_late_rate_7d: float | None = None
    seller_late_rate_30d: float | None = None
    seller_late_rate_90d: float | None = None
    seller_avg_freight_30d: float | None = None
    seller_avg_freight_90d: float | None = None
    seller_avg_basket_30d: float | None = None
    seller_avg_basket_90d: float | None = None
    customer_order_count_30d: float | None = None
    customer_order_count_90d: float | None = None
    customer_late_rate_90d: float | None = None
    category_late_rate_30d: float | None = None
    category_late_rate_90d: float | None = None
    category_order_count_90d: float | None = None

    @field_validator(
        "payment_type_primary",
        "customer_state",
        "seller_state_primary",
        "primary_category",
    )
    @classmethod
    def normalize_str(cls, value: str) -> str:
        return value.strip().lower() if value else "unknown"


class PredictResponse(BaseModel):
    order_id: str
    prediction_id: str
    long_delivery_probability: float = Field(ge=0, le=1)
    risk_band: RiskBand
    model_version: str
    prediction_timestamp: datetime
    feature_timestamp: datetime | None = None
    target: str = "long_delivery_gt_14d"


class ModelInfoResponse(BaseModel):
    model_version: str
    ready: bool
    feature_names: list[str]
    trained_at: str | None = None
    metrics: dict[str, float] | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    ready: bool
    model_version: str | None = None
    detail: str | None = None


class ExplainRequest(PredictRequest):
    """Same feature payload as predict; explanation is a deterministic stub by default."""


class TopFeatureContribution(BaseModel):
    feature: str
    contribution: float


class ExplainResponse(BaseModel):
    order_id: str
    model_version: str
    long_delivery_probability: float = Field(ge=0, le=1)
    top_features: list[TopFeatureContribution]
    method: Literal["stub", "shap"] = "stub"
    note: str | None = None
    target: str = "long_delivery_gt_14d"


class DecideRequest(PredictRequest):
    """Run prediction then expected-value decision. Optionally simulate action."""

    simulate: bool = False
    observed_long_delivery: bool | None = None
    persist_ledger: bool = True


class ActionSimulateRequest(BaseModel):
    order_id: str
    prediction_id: str
    decision_id: str
    action_type: str
    model_version: str
    policy_version: str
    observed_long_delivery: bool
    basket_value: float = Field(ge=0)
    expected_net_value: float | None = None
    persist_ledger: bool = True
