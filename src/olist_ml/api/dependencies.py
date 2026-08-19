"""FastAPI dependency wiring."""

from __future__ import annotations

import secrets
from functools import lru_cache

from fastapi import Header, HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from olist_ml.actions.executor import ActionExecutor
from olist_ml.config import Settings, get_settings
from olist_ml.decisions.service import DecisionService
from olist_ml.inference.predictor import PredictionService
from olist_ml.outcomes.ledger import DecisionLedger

_OPEN_PATHS = frozenset({"/health", "/ready"})


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


def _api_key_ok(supplied: str | None, expected: str) -> bool:
    if not expected or supplied is None:
        return False
    return secrets.compare_digest(supplied.encode(), expected.encode())


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = settings_dep()
    if settings.auth_mode != "api_key":
        return
    if not _api_key_ok(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _settings_for_request(request: Request) -> Settings:
    getter = request.app.dependency_overrides.get(settings_dep, settings_dep)
    return getter()


async def api_key_middleware(request: Request, call_next) -> Response:
    """Gate REST and MCP with the same API key. Probes stay open."""
    settings = _settings_for_request(request)
    path = request.url.path.rstrip("/") or "/"
    if settings.auth_mode != "api_key" or path in _OPEN_PATHS:
        return await call_next(request)
    supplied = request.headers.get("x-api-key")
    if not _api_key_ok(supplied, settings.api_key):
        return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
    return await call_next(request)
