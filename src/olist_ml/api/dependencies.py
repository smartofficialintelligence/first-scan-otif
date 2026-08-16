"""FastAPI dependency wiring."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Header, HTTPException

from olist_ml.actions.executor import ActionExecutor
from olist_ml.config import Settings, get_settings
from olist_ml.decisions.service import DecisionService
from olist_ml.inference.predictor import PredictionService
from olist_ml.outcomes.ledger import DecisionLedger


@lru_cache
def settings_dep() -> Settings:
    return get_settings()


@lru_cache
def prediction_service_dep() -> PredictionService:
    settings = settings_dep()
    service = PredictionService(settings)
    service.load()
    return service


@lru_cache
def decision_service_dep() -> DecisionService:
    settings = settings_dep()
    return DecisionService(config_path=settings.policy_economics_path)


@lru_cache
def action_executor_dep() -> ActionExecutor:
    settings = settings_dep()
    return ActionExecutor(
        config_path=settings.policy_economics_path,
        base_seed=settings.decision_base_seed,
    )


@lru_cache
def decision_ledger_dep() -> DecisionLedger:
    settings = settings_dep()
    return DecisionLedger(settings.decision_ledger_path)


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = settings_dep()
    if settings.auth_mode != "api_key":
        return
    if not settings.api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
