"""MCP server exposing PredictionService tools (no duplicated inference logic).

Uses mcp>=2 MCPServer (FastMCP successor).

Transports:
- stdio: `olist-mcp` / `make mcp-serve` for local agent wiring
- Streamable HTTP: mounted on the FastAPI app at ``/mcp`` (same Cloud Run as REST)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from olist_ml.api.dependencies import prediction_service_dep, settings_dep
from olist_ml.inference.predictor import PredictionService
from olist_ml.logging import setup_logging
from olist_ml.schemas import ExplainRequest, PredictRequest

_service: PredictionService | None = None


def get_service() -> PredictionService:
    global _service
    if _service is None:
        settings = settings_dep()
        setup_logging(settings.log_level)
        svc = prediction_service_dep()
        if not svc.ready:
            svc.load()
        _service = svc
    return _service


def set_service(service: PredictionService) -> None:
    """Test hook: inject a loaded PredictionService."""
    global _service
    _service = service


def _iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _score_kwargs(
    *,
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
) -> dict[str, Any]:
    return {
        "order_id": order_id,
        "seller_id": seller_id,
        "purchase_timestamp": datetime.fromisoformat(purchase_timestamp),
        "prediction_timestamp": _iso(prediction_timestamp),
        "item_count": item_count,
        "basket_value": basket_value,
        "freight_value": freight_value,
        "seller_count": seller_count,
        "category_count": category_count,
        "payment_type_primary": payment_type_primary,
        "installment_count": installment_count,
        "estimated_delivery_horizon_days": estimated_delivery_horizon_days,
        "customer_state": customer_state,
        "seller_state_primary": seller_state_primary,
        "geo_distance_km": geo_distance_km,
        "seller_order_count_7d": seller_order_count_7d,
        "seller_order_count_30d": seller_order_count_30d,
        "seller_order_count_90d": seller_order_count_90d,
        "seller_late_rate_7d": seller_late_rate_7d,
        "seller_late_rate_30d": seller_late_rate_30d,
        "seller_late_rate_90d": seller_late_rate_90d,
        "handling_days": handling_days,
        "remaining_to_promise_days": remaining_to_promise_days,
        "handling_frac_of_promise": handling_frac_of_promise,
        "limit_miss": limit_miss,
        "same_state": same_state,
    }


def predict_promise_miss(
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
    """Score promise-miss risk at carrier handoff via PredictionService.predict_one."""
    svc = service or get_service()
    req = PredictRequest(
        **_score_kwargs(
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
        )
    )
    return svc.predict_one(req).model_dump(mode="json")


def get_model_status(service: PredictionService | None = None) -> dict[str, Any]:
    """Return readiness / model_version via PredictionService.readiness."""
    svc = service or get_service()
    return svc.readiness().model_dump(mode="json")


def get_model_metrics(service: PredictionService | None = None) -> dict[str, Any]:
    """Return model metadata and training metrics via PredictionService.model_info."""
    svc = service or get_service()
    return svc.model_info().model_dump(mode="json")


def explain_promise_miss(
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
    """Stub feature explanation via PredictionService.explain_one (same as REST /v1/explain)."""
    svc = service or get_service()
    req = ExplainRequest(
        **_score_kwargs(
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
        )
    )
    return svc.explain_one(req).model_dump(mode="json")


def create_mcp_server():
    """Build MCPServer with tools bound to PredictionService + decision services."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover
        raise ImportError("mcp package required. Install with: uv sync") from exc

    from olist_ml.tools import decision_tools as dtools

    server = MCPServer(
        name="olist-ml",
        instructions=(
            "Olist promise-miss risk scoring and NOC decision tools at carrier handoff. "
            "Use PredictionService / DecisionService / ActionExecutor paths only; "
            "the agent executes the frozen policy action. Intervention effects are "
            "simulation assumptions, not causal estimates."
        ),
    )

    def _predict_impl(
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
    ) -> dict[str, Any]:
        return predict_promise_miss(
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
        )

    @server.tool(name="predict_promise_miss")
    def _predict_promise_miss(
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
    ) -> dict[str, Any]:
        """Score promise-miss probability at first carrier scan."""
        return _predict_impl(
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
        )

    @server.tool(name="get_model_status")
    def _status() -> dict[str, Any]:
        """Return whether the model artifact is loaded and its version."""
        return get_model_status()

    @server.tool(name="get_model_metrics")
    def _metrics() -> dict[str, Any]:
        """Return model metadata including training metrics when available."""
        return get_model_metrics()

    def _explain_impl(
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
    ) -> dict[str, Any]:
        return explain_promise_miss(
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
        )

    @server.tool(name="explain_promise_miss")
    def _explain_promise_miss(
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
    ) -> dict[str, Any]:
        """Return a stub feature explanation (same path as REST /v1/explain)."""
        return _explain_impl(
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
        )

    @server.tool(name="get_order_risk")
    def _get_order_risk(
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
    ) -> dict[str, Any]:
        """Score promise-miss risk (same path as predict_promise_miss)."""
        return dtools.get_order_risk(
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
        )

    @server.tool(name="list_available_actions")
    def _list_actions() -> dict[str, Any]:
        """List approved intervention actions and simulation economics."""
        return dtools.list_available_actions()

    @server.tool(name="calculate_action_value")
    def _calc_value(
        action: str,
        promise_miss_probability: float,
        basket_value: float,
    ) -> dict[str, Any]:
        """Score one approved action under simulation assumptions (not causal)."""
        return dtools.calculate_action_value(
            action=action,
            probability=promise_miss_probability,
            basket_value=basket_value,
        )

    @server.tool(name="recommend_policy_action")
    def _recommend(
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
        persist_ledger: bool = True,
    ) -> dict[str, Any]:
        """Predict then recommend an action via the deterministic NOC policy."""
        return dtools.recommend_policy_action(
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
            persist_ledger=persist_ledger,
            remaining_to_promise_days=remaining_to_promise_days,
            handling_days=handling_days,
            handling_frac_of_promise=handling_frac_of_promise,
            limit_miss=limit_miss,
            same_state=same_state,
        )

    @server.tool(name="execute_simulated_action")
    def _execute(
        order_id: str,
        prediction_id: str,
        decision_id: str,
        action: str,
        model_version: str,
        policy_version: str,
        basket_value: float,
        observed_promise_miss: bool,
        expected_net_value: float | None = None,
        persist_ledger: bool = True,
    ) -> dict[str, Any]:
        """Simulate an approved intervention via ActionExecutor (no real-world side effects)."""
        return dtools.execute_simulated_action(
            order_id=order_id,
            prediction_id=prediction_id,
            decision_id=decision_id,
            action=action,
            model_version=model_version,
            policy_version=policy_version,
            observed_promise_miss=observed_promise_miss,
            basket_value=basket_value,
            expected_net_value=expected_net_value,
            persist_ledger=persist_ledger,
        )

    @server.tool(name="get_action_outcome")
    def _action_outcome(action_id: str) -> dict[str, Any]:
        """Fetch action/outcome ledger rows for an action_id."""
        return dtools.get_action_outcome(action_id=action_id)

    @server.tool(name="get_decision_history")
    def _decision_history(order_id: str) -> dict[str, Any]:
        """Fetch prediction/decision/action lineage for an order_id."""
        return dtools.get_decision_history(order_id=order_id)

    @server.tool(name="get_policy_metrics")
    def _policy_metrics() -> dict[str, Any]:
        """Return current policy version and simulation economics."""
        return dtools.get_policy_metrics()

    return server


def prepare_streamable_http(
    *,
    json_response: bool = True,
    stateless_http: bool = True,
):
    """Create an ASGI app for Streamable HTTP at whatever path it is mounted on.

    ``json_response=True`` and ``stateless_http=True`` fit Cloud Run (no sticky
    sessions, min instances 0). DNS rebinding protection is off: Cloud Run IAM
    is the gate, and the Host header is the ``*.run.app`` URL not localhost.

    The caller must enter ``server.session_manager.run()`` in the ASGI lifespan
    before serving requests.
    """
    try:
        from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError as exc:  # pragma: no cover
        raise ImportError("mcp package required. Install with: uv sync") from exc

    server = create_mcp_server()
    # Instantiates session_manager (public API). The returned Starlette is unused;
    # we mount StreamableHTTPASGIApp so /mcp and /mcp/ both hit the transport.
    server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=json_response,
        stateless_http=stateless_http,
        host="0.0.0.0",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return server, StreamableHTTPASGIApp(server.session_manager)


def main() -> None:
    server = create_mcp_server()
    get_service()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
