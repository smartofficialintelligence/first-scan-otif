"""HTTP routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from olist_ml.api.dependencies import prediction_service_dep, verify_api_key
from olist_ml.inference.predictor import PredictionService
from olist_ml.monitoring.metrics import get_metrics
from olist_ml.schemas import (
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
