"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI

from olist_ml.api.dependencies import prediction_service_dep, settings_dep
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

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        service = prediction_service_dep()
        service.load()
        set_service(service)
        if mcp_server is not None:
            async with mcp_server.session_manager.run():
                yield
        else:
            yield

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    if mcp_asgi is not None:
        # Streamable HTTP (same IAM / champion as REST). stdio remains via olist-mcp.
        app.mount("/mcp", mcp_asgi)
    return app


app = create_app()


def run() -> None:
    settings = settings_dep()
    uvicorn.run("olist_ml.api.app:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
