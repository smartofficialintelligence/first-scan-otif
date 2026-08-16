"""HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from olist_ml.actions.executor import ActionExecutor
from olist_ml.actions.schemas import ActionRequest
from olist_ml.api.dependencies import (
    action_executor_dep,
    decision_ledger_dep,
    decision_service_dep,
    prediction_service_dep,
    verify_api_key,
)
from olist_ml.decisions.schemas import ActionType
from olist_ml.decisions.service import DecisionService
from olist_ml.inference.predictor import PredictionService
from olist_ml.monitoring.metrics import get_metrics
from olist_ml.outcomes.ledger import DecisionLedger
from olist_ml.schemas import (
    ActionSimulateRequest,
    DecideRequest,
    ExplainRequest,
    ExplainResponse,
    HealthResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    ReadyResponse,
)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
def ready(service: PredictionService = Depends(prediction_service_dep)) -> ReadyResponse:
    return service.readiness()


@router.get("/v1/metrics")
def metrics() -> dict[str, Any]:
    """In-process service + ML metrics snapshot (JSON)."""
    return get_metrics().snapshot()


@router.get("/v1/model", response_model=ModelInfoResponse, dependencies=[Depends(verify_api_key)])
def model_info(service: PredictionService = Depends(prediction_service_dep)) -> ModelInfoResponse:
    return service.model_info()


@router.post("/v1/predict", response_model=PredictResponse, dependencies=[Depends(verify_api_key)])
def predict(
    body: PredictRequest,
    service: PredictionService = Depends(prediction_service_dep),
) -> PredictResponse:
    if not service.ready:
        raise HTTPException(status_code=503, detail="Model not ready")
    try:
        return service.predict_one(body)
    except Exception as exc:  # noqa: BLE001 — surface as 400 for bad feature payloads
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/v1/explain", response_model=ExplainResponse, dependencies=[Depends(verify_api_key)])
def explain(
    body: ExplainRequest,
    service: PredictionService = Depends(prediction_service_dep),
) -> ExplainResponse:
    if not service.ready:
        raise HTTPException(status_code=503, detail="Model not ready")
    try:
        return service.explain_one(body)
    except Exception as exc:  # noqa: BLE001 — surface as 400 for bad feature payloads
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/v1/policies/current", dependencies=[Depends(verify_api_key)])
def current_policy(decision_svc: DecisionService = Depends(decision_service_dep)) -> dict[str, Any]:
    cfg = decision_svc.config
    return {
        "policy_version": cfg.policy_version,
        "policy_config_version": cfg.policy_config_version,
        "assumptions_disclaimer": cfg.assumptions_disclaimer,
        "actions": {
            k.value: {
                "cost": v.cost,
                "risk_prevention_probability": v.risk_prevention_probability,
                "customer_impact_reduction": v.customer_impact_reduction,
                "eligible": v.eligible,
            }
            for k, v in cfg.actions.items()
        },
        "business_loss": cfg.business_loss.model_dump(),
        "routing": cfg.routing.model_dump(),
    }


@router.post("/v1/decision", dependencies=[Depends(verify_api_key)])
def decide(
    body: DecideRequest,
    pred_svc: PredictionService = Depends(prediction_service_dep),
    decision_svc: DecisionService = Depends(decision_service_dep),
    executor: ActionExecutor = Depends(action_executor_dep),
    ledger: DecisionLedger = Depends(decision_ledger_dep),
) -> dict[str, Any]:
    if not pred_svc.ready:
        raise HTTPException(status_code=503, detail="Model not ready")
    try:
        prediction = pred_svc.predict_one(body)
        decision = decision_svc.decide_from_prediction(
            prediction,
            basket_value=body.basket_value,
            seller_id=body.seller_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.persist_ledger:
        ledger.append_prediction(prediction)
        ledger.append_decision(decision)

    out: dict[str, Any] = {
        "prediction": prediction.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
    }

    if body.simulate:
        if body.observed_long_delivery is None:
            raise HTTPException(
                status_code=400,
                detail="observed_long_delivery is required when simulate=true",
            )
        action = executor.execute_decision(
            decision_id=decision.decision_id,
            prediction_id=prediction.prediction_id,
            order_id=prediction.order_id,
            action_type=decision.recommended_action,
            model_version=prediction.model_version,
            policy_version=decision.policy_version,
            observed_long_delivery=body.observed_long_delivery,
            basket_value=body.basket_value,
            expected_net_value=decision.expected_net_value,
        )
        if body.persist_ledger:
            ledger.append_action(action)
            ledger.append_outcome(
                {
                    "order_id": action.order_id,
                    "action_id": action.action_id,
                    "decision_id": action.decision_id,
                    "observed_long_delivery": action.observed_long_delivery,
                    "simulated_long_delivery": action.simulated_long_delivery,
                    "simulated_net_value": action.simulated_net_value,
                    "simulated_gross_avoided_loss": action.simulated_gross_avoided_loss,
                    "note": "simulated_outcome_only",
                }
            )
        out["action"] = action.model_dump(mode="json")

    return out


@router.post("/v1/action/simulate", dependencies=[Depends(verify_api_key)])
def simulate_action(
    body: ActionSimulateRequest,
    executor: ActionExecutor = Depends(action_executor_dep),
    ledger: DecisionLedger = Depends(decision_ledger_dep),
) -> dict[str, Any]:
    try:
        action_type = ActionType(body.action_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid action_type: {body.action_type}") from exc
    try:
        result = executor.execute(
            ActionRequest(
                order_id=body.order_id,
                prediction_id=body.prediction_id,
                decision_id=body.decision_id,
                action_type=action_type,
                model_version=body.model_version,
                policy_version=body.policy_version,
                expected_net_value=body.expected_net_value,
                observed_long_delivery=body.observed_long_delivery,
                basket_value=body.basket_value,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.persist_ledger:
        ledger.append_action(result)
        ledger.append_outcome(
            {
                "order_id": result.order_id,
                "action_id": result.action_id,
                "decision_id": result.decision_id,
                "observed_long_delivery": result.observed_long_delivery,
                "simulated_long_delivery": result.simulated_long_delivery,
                "simulated_net_value": result.simulated_net_value,
                "note": "simulated_outcome_only",
            }
        )
    return result.model_dump(mode="json")


@router.get("/v1/orders/{order_id}/decision", dependencies=[Depends(verify_api_key)])
def order_decision_history(
    order_id: str,
    ledger: DecisionLedger = Depends(decision_ledger_dep),
) -> dict[str, Any]:
    rows = ledger.for_order(order_id)
    return {"order_id": order_id, "records": rows}
