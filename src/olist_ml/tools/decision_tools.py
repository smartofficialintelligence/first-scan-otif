"""Decision MCP tool handlers — thin wrappers over domain services (no duplicated policy logic)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from olist_ml.actions.executor import ActionExecutor
from olist_ml.actions.schemas import ActionRequest
from olist_ml.api.dependencies import (
    action_executor_dep,
    decision_ledger_dep,
    decision_service_dep,
    prediction_service_dep,
    settings_dep,
)
from olist_ml.decisions.schemas import ActionType
from olist_ml.decisions.service import DecisionService
from olist_ml.decisions.value import business_loss_if_miss, score_action
from olist_ml.features.assembler import noc_context_from_request
from olist_ml.inference.predictor import PredictionService
from olist_ml.logging import setup_logging
from olist_ml.outcomes.ledger import DecisionLedger
from olist_ml.schemas import PredictRequest, PredictResponse

_pred_svc: PredictionService | None = None
_decision_svc: DecisionService | None = None
_executor: ActionExecutor | None = None
_ledger: DecisionLedger | None = None


def get_prediction_service() -> PredictionService:
    global _pred_svc
    if _pred_svc is None:
        settings = settings_dep()
        setup_logging(settings.log_level)
        svc = prediction_service_dep()
        if not svc.ready:
            svc.load()
        _pred_svc = svc
    return _pred_svc


def get_decision_service() -> DecisionService:
    global _decision_svc
    if _decision_svc is None:
        settings = settings_dep()
        setup_logging(settings.log_level)
        _decision_svc = decision_service_dep()
    return _decision_svc


def get_executor() -> ActionExecutor:
    global _executor
    if _executor is None:
        _executor = action_executor_dep()
    return _executor


def get_ledger() -> DecisionLedger:
    global _ledger
    if _ledger is None:
        _ledger = decision_ledger_dep()
    return _ledger


def set_decision_deps(
    *,
    prediction_service: PredictionService | None = None,
    decision_service: DecisionService | None = None,
    executor: ActionExecutor | None = None,
    ledger: DecisionLedger | None = None,
) -> None:
    """Test hook for injecting decision-layer dependencies."""
    global _pred_svc, _decision_svc, _executor, _ledger
    if prediction_service is not None:
        _pred_svc = prediction_service
    if decision_service is not None:
        _decision_svc = decision_service
    if executor is not None:
        _executor = executor
    if ledger is not None:
        _ledger = ledger


def _predict_request(**kwargs: Any) -> PredictRequest:
    purchase_timestamp = kwargs.pop("purchase_timestamp")
    prediction_timestamp = kwargs.pop("prediction_timestamp", None)
    return PredictRequest(
        purchase_timestamp=datetime.fromisoformat(purchase_timestamp),
        prediction_timestamp=(
            datetime.fromisoformat(prediction_timestamp) if prediction_timestamp else None
        ),
        **kwargs,
    )


def get_order_risk(
    order_id: str,
    seller_id: str,
    purchase_timestamp: str,
    item_count: int,
    basket_value: float,
    freight_value: float,
    estimated_delivery_horizon_days: float,
    prediction_timestamp: str | None = None,
    seller_count: int = 1,
    category_count: int = 1,
    payment_type_primary: str = "unknown",
    installment_count: int = 1,
    customer_state: str = "unknown",
    seller_state_primary: str = "unknown",
    geo_distance_km: float = 0.0,
    seller_order_count_7d: float | None = None,
    seller_order_count_30d: float | None = None,
    seller_order_count_90d: float | None = None,
    seller_late_rate_7d: float | None = None,
    seller_late_rate_30d: float | None = None,
    seller_late_rate_90d: float | None = None,
    handling_days: float | None = None,
    remaining_to_promise_days: float | None = None,
    handling_frac_of_promise: float | None = None,
    limit_miss: float | None = None,
    same_state: float | None = None,
    service: PredictionService | None = None,
) -> dict[str, Any]:
    """Return promise-miss risk via PredictionService."""
    svc = service or get_prediction_service()
    req = _predict_request(
        order_id=order_id,
        seller_id=seller_id,
        purchase_timestamp=purchase_timestamp,
        prediction_timestamp=prediction_timestamp,
        item_count=item_count,
        basket_value=basket_value,
        freight_value=freight_value,
        estimated_delivery_horizon_days=estimated_delivery_horizon_days,
        seller_count=seller_count,
        category_count=category_count,
        payment_type_primary=payment_type_primary,
        installment_count=installment_count,
        customer_state=customer_state,
        seller_state_primary=seller_state_primary,
        geo_distance_km=geo_distance_km,
        seller_order_count_7d=seller_order_count_7d,
        seller_order_count_30d=seller_order_count_30d,
        seller_order_count_90d=seller_order_count_90d,
        seller_late_rate_7d=seller_late_rate_7d,
        seller_late_rate_30d=seller_late_rate_30d,
        seller_late_rate_90d=seller_late_rate_90d,
        handling_days=handling_days,
        remaining_to_promise_days=remaining_to_promise_days,
        handling_frac_of_promise=handling_frac_of_promise,
        limit_miss=limit_miss,
        same_state=same_state,
    )
    return svc.predict_one(req).model_dump(mode="json")


def list_available_actions(
    decision_service: DecisionService | None = None,
) -> dict[str, Any]:
    """List approved actions and their simulation economics from versioned config."""
    svc = decision_service or get_decision_service()
    cfg = svc.config
    return {
        "policy_version": cfg.policy_version,
        "policy_config_version": cfg.policy_config_version,
        "assumptions_disclaimer": cfg.assumptions_disclaimer,
        "economics_gate": cfg.economics_gate.model_dump(),
        "simulation_claims_allowed": cfg.economics_gate.simulation_claims_allowed,
        "causal_roi_claim_allowed": cfg.economics_gate.causal_roi_claim_allowed,
        "actions": [
            {
                "action": a.value,
                "cost": e.cost,
                "risk_prevention_probability": e.risk_prevention_probability,
                "customer_impact_reduction": e.customer_impact_reduction,
                "eligible": e.eligible,
            }
            for a, e in cfg.actions.items()
            if e.eligible
        ],
    }


def calculate_action_value(
    action: str,
    probability: float,
    basket_value: float,
    decision_service: DecisionService | None = None,
) -> dict[str, Any]:
    """Score one approved action under simulation assumptions (not causal)."""
    svc = decision_service or get_decision_service()
    try:
        action_type = ActionType(action)
    except ValueError as exc:
        raise ValueError(f"Unknown action: {action}") from exc
    econ = svc.config.actions.get(action_type)
    if econ is None or not econ.eligible:
        raise ValueError(f"Action not eligible: {action}")
    loss = business_loss_if_miss(basket_value, svc.config.business_loss)
    candidate = score_action(
        action=econ,
        probability=probability,
        loss_if_miss=loss,
    )
    return {
        "business_loss_if_miss": loss,
        "assumptions_disclaimer": svc.config.assumptions_disclaimer,
        "candidate": candidate.model_dump(mode="json"),
    }


def recommend_policy_action(
    order_id: str,
    seller_id: str,
    purchase_timestamp: str,
    item_count: int,
    basket_value: float,
    freight_value: float,
    estimated_delivery_horizon_days: float,
    prediction_timestamp: str | None = None,
    seller_count: int = 1,
    category_count: int = 1,
    payment_type_primary: str = "unknown",
    installment_count: int = 1,
    customer_state: str = "unknown",
    seller_state_primary: str = "unknown",
    geo_distance_km: float = 0.0,
    seller_order_count_7d: float | None = None,
    seller_order_count_30d: float | None = None,
    seller_order_count_90d: float | None = None,
    seller_late_rate_7d: float | None = None,
    seller_late_rate_30d: float | None = None,
    seller_late_rate_90d: float | None = None,
    persist_ledger: bool = True,
    remaining_to_promise_days: float | None = None,
    handling_days: float | None = None,
    handling_frac_of_promise: float | None = None,
    limit_miss: float | None = None,
    same_state: float | None = None,
    service: PredictionService | None = None,
    decision_service: DecisionService | None = None,
    ledger: DecisionLedger | None = None,
) -> dict[str, Any]:
    """Predict then run deterministic NOC policy (same services as REST /v1/decision)."""
    pred_body = get_order_risk(
        order_id=order_id,
        seller_id=seller_id,
        purchase_timestamp=purchase_timestamp,
        item_count=item_count,
        basket_value=basket_value,
        freight_value=freight_value,
        estimated_delivery_horizon_days=estimated_delivery_horizon_days,
        prediction_timestamp=prediction_timestamp,
        seller_count=seller_count,
        category_count=category_count,
        payment_type_primary=payment_type_primary,
        installment_count=installment_count,
        customer_state=customer_state,
        seller_state_primary=seller_state_primary,
        geo_distance_km=geo_distance_km,
        seller_order_count_7d=seller_order_count_7d,
        seller_order_count_30d=seller_order_count_30d,
        seller_order_count_90d=seller_order_count_90d,
        seller_late_rate_7d=seller_late_rate_7d,
        seller_late_rate_30d=seller_late_rate_30d,
        seller_late_rate_90d=seller_late_rate_90d,
        handling_days=handling_days,
        remaining_to_promise_days=remaining_to_promise_days,
        handling_frac_of_promise=handling_frac_of_promise,
        limit_miss=limit_miss,
        same_state=same_state,
        service=service,
    )
    prediction = PredictResponse.model_validate(pred_body)
    dsvc = decision_service or get_decision_service()
    req = _predict_request(
        order_id=order_id,
        seller_id=seller_id,
        purchase_timestamp=purchase_timestamp,
        prediction_timestamp=prediction_timestamp,
        item_count=item_count,
        basket_value=basket_value,
        freight_value=freight_value,
        estimated_delivery_horizon_days=estimated_delivery_horizon_days,
        seller_count=seller_count,
        category_count=category_count,
        payment_type_primary=payment_type_primary,
        installment_count=installment_count,
        customer_state=customer_state,
        seller_state_primary=seller_state_primary,
        geo_distance_km=geo_distance_km,
        remaining_to_promise_days=remaining_to_promise_days,
        handling_days=handling_days,
        same_state=same_state,
    )
    noc = noc_context_from_request(req)
    decision = dsvc.decide_from_prediction(
        prediction,
        basket_value=basket_value,
        seller_id=seller_id,
        remaining_to_promise_days=noc["remaining_to_promise_days"],
        geo_distance_km=noc["geo_distance_km"],
        same_state=noc["same_state"],
        freight_value=noc["freight_value"],
        p1_score_threshold=prediction.p1_score_threshold,
        p2_score_threshold=prediction.p2_score_threshold,
    )
    if persist_ledger:
        led = ledger or get_ledger()
        led.append_prediction(prediction)
        led.append_decision(decision)
    return {
        "prediction": prediction.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
    }


def execute_simulated_action(
    order_id: str,
    prediction_id: str,
    decision_id: str,
    action: str,
    model_version: str,
    policy_version: str,
    basket_value: float,
    observed_promise_miss: bool,
    expected_net_value: float | None = None,
    freight_value: float | None = None,
    intervention_cost: float | None = None,
    persist_ledger: bool = True,
    executor: ActionExecutor | None = None,
    ledger: DecisionLedger | None = None,
) -> dict[str, Any]:
    """Run ActionExecutor simulation for an approved action."""
    try:
        action_type = ActionType(action)
    except ValueError as exc:
        raise ValueError(f"Unknown action: {action}") from exc
    ex = executor or get_executor()
    result = ex.execute(
        ActionRequest(
            order_id=order_id,
            prediction_id=prediction_id,
            decision_id=decision_id,
            action_type=action_type,
            model_version=model_version,
            policy_version=policy_version,
            expected_net_value=expected_net_value,
            observed_promise_miss=observed_promise_miss,
            basket_value=basket_value,
            freight_value=freight_value,
            intervention_cost=intervention_cost,
        )
    )
    if persist_ledger:
        led = ledger or get_ledger()
        led.append_action(result)
        led.append_outcome(
            {
                "order_id": result.order_id,
                "action_id": result.action_id,
                "decision_id": result.decision_id,
                "observed_promise_miss": result.observed_promise_miss,
                "simulated_promise_miss": result.simulated_promise_miss,
                "simulated_net_value": result.simulated_net_value,
                "note": "simulated_outcome_only",
            }
        )
    return result.model_dump(mode="json")


def get_action_outcome(
    action_id: str,
    ledger: DecisionLedger | None = None,
) -> dict[str, Any]:
    """Lookup action/outcome records by action_id from the local ledger."""
    led = ledger or get_ledger()
    rows = [r for r in led.read_all() if r.get("action_id") == action_id]
    return {"action_id": action_id, "records": rows}


def get_decision_history(
    order_id: str,
    ledger: DecisionLedger | None = None,
) -> dict[str, Any]:
    """Return ledger lineage for an order_id."""
    led = ledger or get_ledger()
    return {"order_id": order_id, "records": led.for_order(order_id)}


def get_policy_metrics(
    decision_service: DecisionService | None = None,
) -> dict[str, Any]:
    """Return current policy version + economics (simulation assumptions)."""
    return list_available_actions(decision_service=decision_service)
