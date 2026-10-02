"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from hoje import __version__
from hoje.api import api_router
from hoje.api.health import router as health_router
from hoje.config import get_settings
from hoje.db import dispose_engine
from hoje.errors import install_exception_handlers
from hoje.logging import configure_logging, get_logger
from hoje.request_context import ClientIdMiddleware
from hoje.services.realtime import RealtimeHub, dsn_from_url

OPENAPI_URL = "/api/v1/openapi.json"
DOCS_URL = "/api/docs"


def _operation_id(route: APIRoute) -> str:
    return route.name


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()  # fail fast on invalid configuration
    configure_logging(settings.log_level)
    get_logger(__name__).info("startup", env=settings.env, version=__version__)
    hub = RealtimeHub(dsn_from_url(settings.database_url))
    _app.state.hub = hub
    await hub.start()
    try:
        yield
    finally:
        await hub.stop()
        await dispose_engine()


def create_app(*, docs_enabled: bool | None = None) -> FastAPI:
    """Build the app.

    ``docs_enabled`` defaults to ``HOJE_ENV != production``. The OpenAPI exporter passes
    ``False`` so that generating the spec needs no configuration and no database.
    """
    if docs_enabled is None:
        docs_enabled = not get_settings().is_production
    app = FastAPI(
        title="Hoje API",
        version=__version__,
        description="Self-hosted personal planner.",
        openapi_url=OPENAPI_URL,
        docs_url=DOCS_URL if docs_enabled else None,
        redoc_url=None,
        generate_unique_id_function=_operation_id,
        lifespan=_lifespan,
    )
    app.add_middleware(ClientIdMiddleware)
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    return app


def __getattr__(name: str) -> FastAPI:
    """Lazily build ``hoje.main:app`` so importing this module needs no configuration."""
    if name == "app":
        instance = create_app()
        globals()["app"] = instance
        return instance
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
