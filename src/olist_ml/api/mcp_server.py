"""MCP server exposing PredictionService tools (no duplicated inference logic).

Uses mcp>=2 MCPServer (FastMCP successor). Install with: uv sync --extra mcp
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


def predict_long_delivery(
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
    service: PredictionService | None = None,
) -> dict[str, Any]:
    """Score late-delivery risk for one order via PredictionService.predict_one."""
    svc = service or get_service()
    req = PredictRequest(
        order_id=order_id,
        seller_id=seller_id,
        purchase_timestamp=datetime.fromisoformat(purchase_timestamp),
        prediction_timestamp=(
            datetime.fromisoformat(prediction_timestamp) if prediction_timestamp else None
        ),
        item_count=item_count,
        basket_value=basket_value,
        freight_value=freight_value,
        seller_count=seller_count,
        category_count=category_count,
        payment_type_primary=payment_type_primary,
        installment_count=installment_count,
        estimated_delivery_horizon_days=estimated_delivery_horizon_days,
        customer_state=customer_state,
        seller_state_primary=seller_state_primary,
        geo_distance_km=geo_distance_km,
        seller_order_count_7d=seller_order_count_7d,
        seller_order_count_30d=seller_order_count_30d,
        seller_order_count_90d=seller_order_count_90d,
        seller_late_rate_7d=seller_late_rate_7d,
        seller_late_rate_30d=seller_late_rate_30d,
        seller_late_rate_90d=seller_late_rate_90d,
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


def explain_long_delivery(
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
    service: PredictionService | None = None,
) -> dict[str, Any]:
    """Stub feature explanation via PredictionService.explain_one (same as REST /v1/explain)."""
    svc = service or get_service()
    req = ExplainRequest(
        order_id=order_id,
        seller_id=seller_id,
        purchase_timestamp=datetime.fromisoformat(purchase_timestamp),
        prediction_timestamp=(
            datetime.fromisoformat(prediction_timestamp) if prediction_timestamp else None
        ),
        item_count=item_count,
        basket_value=basket_value,
        freight_value=freight_value,
        seller_count=seller_count,
        category_count=category_count,
        payment_type_primary=payment_type_primary,
        installment_count=installment_count,
        estimated_delivery_horizon_days=estimated_delivery_horizon_days,
        customer_state=customer_state,
        seller_state_primary=seller_state_primary,
        geo_distance_km=geo_distance_km,
        seller_order_count_7d=seller_order_count_7d,
        seller_order_count_30d=seller_order_count_30d,
        seller_order_count_90d=seller_order_count_90d,
        seller_late_rate_7d=seller_late_rate_7d,
        seller_late_rate_30d=seller_late_rate_30d,
        seller_late_rate_90d=seller_late_rate_90d,
    )
    return svc.explain_one(req).model_dump(mode="json")


def create_mcp_server():
    """Build MCPServer with tools bound to PredictionService + decision services."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "mcp package required. Install with: uv sync --extra mcp"
        ) from exc

    from olist_ml.tools import decision_tools as dtools

    server = MCPServer(
        name="olist-ml",
        instructions=(
            "Olist long-delivery risk scoring and expected-value decision tools. "
            "Use PredictionService / DecisionService / ActionExecutor paths only; "
            "intervention effects are simulation assumptions, not causal estimates."
        ),
    )

    @server.tool(name="predict_long_delivery")
    def _predict(
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
    ) -> dict[str, Any]:
        """Score long-delivery probability for an order."""
        return predict_long_delivery(
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
        )

    @server.tool(name="get_model_status")
    def _status() -> dict[str, Any]:
        """Return whether the model artifact is loaded and its version."""
        return get_model_status()

    @server.tool(name="get_model_metrics")
    def _metrics() -> dict[str, Any]:
        """Return model metadata including training metrics when available."""
        return get_model_metrics()

    @server.tool(name="explain_long_delivery")
    def _explain(
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
    ) -> dict[str, Any]:
        """Return a stub feature explanation (same path as REST /v1/explain)."""
        return explain_long_delivery(
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
    ) -> dict[str, Any]:
        """Alias of predict_long_delivery for agent tool naming."""
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
        )

    @server.tool(name="list_available_actions")
    def _list_actions() -> dict[str, Any]:
        """List approved intervention actions and simulation economics."""
        return dtools.list_available_actions()

    @server.tool(name="calculate_action_value")
    def _calc_value(
        action: str,
        long_delivery_probability: float,
        basket_value: float,
    ) -> dict[str, Any]:
        """Compute expected value for one approved action (simulation assumptions)."""
        return dtools.calculate_action_value(
            action=action,
            long_delivery_probability=long_delivery_probability,
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
        persist_ledger: bool = True,
    ) -> dict[str, Any]:
        """Predict then recommend an action via the deterministic EV policy."""
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
        )

    @server.tool(name="execute_simulated_action")
    def _execute(
        order_id: str,
        prediction_id: str,
        decision_id: str,
        action: str,
        model_version: str,
        policy_version: str,
        observed_long_delivery: bool,
        basket_value: float,
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
            observed_long_delivery=observed_long_delivery,
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


def main() -> None:
    server = create_mcp_server()
    get_service()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
