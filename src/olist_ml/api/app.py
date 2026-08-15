"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from olist_ml.api.dependencies import prediction_service_dep, settings_dep
from olist_ml.api.routes import router
from olist_ml.logging import setup_logging


def create_app() -> FastAPI:
    settings = settings_dep()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        service = prediction_service_dep()
        service.load()
        yield

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    settings = settings_dep()
    uvicorn.run("olist_ml.api.app:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
