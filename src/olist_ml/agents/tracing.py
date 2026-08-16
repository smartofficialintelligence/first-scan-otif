"""Optional LangSmith / LangChain tracing for agent review (D9).

Enabled when LANGSMITH_API_KEY or LANGCHAIN_API_KEY is set and
LANGCHAIN_TRACING_V2 is not explicitly "false".
"""

from __future__ import annotations

import os
from typing import Any


def tracing_enabled() -> bool:
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() in {"0", "false", "no"}:
        return False
    return bool(os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"))


def configure_tracing() -> dict[str, Any]:
    """Apply env defaults for LangSmith; no-op when disabled or SDK missing."""
    status = {
        "enabled": False,
        "project": (
            os.getenv("LANGCHAIN_PROJECT")
            or os.getenv("LANGSMITH_PROJECT")
            or "olist-ml-agent"
        ),
        "reason": "disabled",
    }
    if not tracing_enabled():
        status["reason"] = "no_api_key_or_explicitly_disabled"
        return status
    try:
        import langsmith  # noqa: F401
    except ImportError:
        status["reason"] = "langsmith_not_installed"
        return status

    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", status["project"])
    # Prefer LANGSMITH_API_KEY; LangChain also accepts LANGCHAIN_API_KEY.
    if os.getenv("LANGSMITH_API_KEY") and not os.getenv("LANGCHAIN_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = os.environ["LANGSMITH_API_KEY"]
    status["enabled"] = True
    status["reason"] = "configured"
    return status


def trace_metadata(order_id: str | None = None, prediction_id: str | None = None) -> dict[str, Any]:
    meta = {"component": "agent_review", "simulation_only": True}
    if order_id:
        meta["order_id"] = order_id
    if prediction_id:
        meta["prediction_id"] = prediction_id
    return meta
