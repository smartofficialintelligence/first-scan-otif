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
    """Build MCPServer with tools bound to PredictionService handlers."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "mcp package required. Install with: uv sync --extra mcp"
        ) from exc

    server = MCPServer(
        name="olist-ml",
        instructions="Olist late-delivery risk scoring via shared PredictionService.",
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
        """Score late-delivery probability for an order."""
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

    return server


def main() -> None:
    server = create_mcp_server()
    get_service()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
