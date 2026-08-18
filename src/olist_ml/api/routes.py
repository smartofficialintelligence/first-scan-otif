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
from olist_ml.features.assembler import noc_context_from_request
from olist_ml.inference.predictor import PredictionService
from olist_ml.monitoring.metrics import get_metrics
from olist_ml.outcomes.ledger import DecisionLedger
from olist_ml.schemas import (
    ActionSimulateRequest,
    AgentReviewRequest,
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
        "economics_gate": cfg.economics_gate.model_dump(),
        "simulation_claims_allowed": cfg.economics_gate.simulation_claims_allowed,
        "causal_roi_claim_allowed": cfg.economics_gate.causal_roi_claim_allowed,
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
        "noc_policy": cfg.noc_policy.model_dump(),
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
        noc = noc_context_from_request(body)
        meta = pred_svc._meta  # noqa: SLF001
        decision = decision_svc.decide_from_prediction(
            prediction,
            basket_value=body.basket_value,
            seller_id=body.seller_id,
            remaining_to_promise_days=noc["remaining_to_promise_days"],
            geo_distance_km=noc["geo_distance_km"],
            same_state=noc["same_state"],
            freight_value=noc["freight_value"],
            p1_score_threshold=None if meta is None else meta.p1_score_threshold,
            p2_score_threshold=None if meta is None else meta.p2_score_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if body.persist_ledger:
        ledger.append_prediction(prediction)
        ledger.append_decision(decision)

    get_metrics().observe_decision(recommended_action=decision.recommended_action.value)

    out: dict[str, Any] = {
        "prediction": prediction.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
    }

    if body.simulate:
        if body.observed_promise_miss is None:
            raise HTTPException(
                status_code=400,
                detail="observed_promise_miss is required when simulate=true",
            )
        action = executor.execute_decision(
            decision_id=decision.decision_id,
            prediction_id=prediction.prediction_id,
            order_id=prediction.order_id,
            action_type=decision.recommended_action,
            model_version=prediction.model_version,
            policy_version=decision.policy_version,
            observed_promise_miss=body.observed_promise_miss,
            basket_value=body.basket_value,
            expected_net_value=decision.expected_net_value,
            freight_value=body.freight_value,
            intervention_cost=decision.upgrade_cost,
        )
        if body.persist_ledger:
            ledger.append_action(action)
            ledger.append_outcome(
                {
                    "order_id": action.order_id,
                    "action_id": action.action_id,
                    "decision_id": action.decision_id,
                    "observed_promise_miss": action.observed_promise_miss,
                    "simulated_promise_miss": action.simulated_promise_miss,
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
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action_type: {body.action_type}",
        ) from exc
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
                observed_promise_miss=body.observed_promise_miss,
                basket_value=body.basket_value,
                freight_value=body.freight_value,
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
                "observed_promise_miss": result.observed_promise_miss,
                "simulated_promise_miss": result.simulated_promise_miss,
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


@router.get("/v1/actions/{action_id}", dependencies=[Depends(verify_api_key)])
def action_lookup(
    action_id: str,
    ledger: DecisionLedger = Depends(decision_ledger_dep),
) -> dict[str, Any]:
    rows = ledger.for_action(action_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No ledger records for action_id={action_id}")
    return {"action_id": action_id, "records": rows}


@router.post("/v1/agent/review", dependencies=[Depends(verify_api_key)])
def agent_review(body: AgentReviewRequest) -> dict[str, Any]:
    """LangGraph bounded agent review (tool-driven; optional human gate)."""
    try:
        from olist_ml.agents.graph import run_agent_review
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="Agent extras required. Install with: uv sync --extra agent",
        ) from exc

    result = run_agent_review(
        {
            "order_id": body.order_id,
            "prediction_id": body.prediction_id,
            "model_version": body.model_version,
            "promise_miss_probability": body.promise_miss_probability,
            "basket_value": body.basket_value,
            "seller_id": body.seller_id,
            "remaining_to_promise_days": body.remaining_to_promise_days,
            "geo_distance_km": body.geo_distance_km,
            "same_state": body.same_state,
            "freight_value": body.freight_value,
            "p1_score_threshold": body.p1_score_threshold,
            "p2_score_threshold": body.p2_score_threshold,
            "observed_promise_miss": body.observed_promise_miss,
            "run_simulation": body.run_simulation,
            "require_human_approval": body.require_human_approval,
            "human_approved": body.human_approved,
            "tool_trace": [],
        }
    )
    action_result = result.get("action_result") or {}
    get_metrics().observe_agent_review(
        status=str(result.get("status") or "unknown"),
        action=result.get("selected_action"),
        spend=float(action_result.get("simulated_cost") or 0.0),
        net=float(action_result.get("simulated_net_value") or 0.0),
    )
    return {
        "status": result.get("status"),
        "selected_action": result.get("selected_action"),
        "agent_rationale": result.get("agent_rationale"),
        "policy_recommendation": result.get("policy_recommendation"),
        "action_values": result.get("action_values"),
        "tool_trace": result.get("tool_trace"),
        "action_result": action_result or None,
        "decision_id": result.get("decision_id"),
        "error": result.get("error"),
        "langsmith": result.get("langsmith"),
    }
