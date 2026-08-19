"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from starlette.routing import Route

from olist_ml.api.dependencies import (
    action_executor_dep,
    api_key_middleware,
    decision_ledger_dep,
    decision_service_dep,
    prediction_service_dep,
    settings_dep,
)
from olist_ml.api.mcp_server import prepare_streamable_http, set_service
from olist_ml.api.routes import router
from olist_ml.logging import setup_logging


def create_app() -> FastAPI:
    settings = settings_dep()
    setup_logging(settings.log_level)

    mcp_server: Any = None
    mcp_asgi: Any = None
    try:
        mcp_server, mcp_asgi = prepare_streamable_http()
    except ImportError:
        mcp_server, mcp_asgi = None, None

    def _dep(app: FastAPI, dep):  # noqa: ANN001
        return app.dependency_overrides.get(dep, dep)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Honor FastAPI overrides so TestClient and production share one wiring path.
        service = _dep(_app, prediction_service_dep)()
        if not service.ready:
            service.load()
        set_service(service)
        from olist_ml.tools.decision_tools import set_decision_deps

        set_decision_deps(
            prediction_service=service,
            decision_service=_dep(_app, decision_service_dep)(),
            executor=_dep(_app, action_executor_dep)(),
            ledger=_dep(_app, decision_ledger_dep)(),
        )
        if mcp_server is not None:
            async with mcp_server.session_manager.run():
                yield
        else:
            yield

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.middleware("http")(api_key_middleware)
    app.include_router(router)
    if mcp_asgi is not None:
        # Route (not Mount) so POST /mcp is 200, not a 307 to /mcp/.
        mcp_methods = ["GET", "POST", "DELETE"]
        app.router.routes.extend(
            [
                Route("/mcp", endpoint=mcp_asgi, methods=mcp_methods),
                Route("/mcp/", endpoint=mcp_asgi, methods=mcp_methods),
            ]
        )
    return app


app = create_app()


def run() -> None:
    settings = settings_dep()
    uvicorn.run("olist_ml.api.app:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
