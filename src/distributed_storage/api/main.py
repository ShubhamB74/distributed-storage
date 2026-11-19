"""Application factory.

Run with: ``uvicorn --factory distributed_storage.api.main:create_app``
The factory (instead of a module-level ``app``) means configuration is loaded at startup,
so missing secrets stop the process immediately and imports stay side-effect free.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from distributed_storage import __version__
from distributed_storage.api.health import router as health_router
from distributed_storage.api.middleware import RequestContextMiddleware
from distributed_storage.core.config import Settings, get_settings
from distributed_storage.core.logging import configure_logging
from distributed_storage.db.engine import create_engine
from distributed_storage.db.migrations import get_expected_head
from distributed_storage.db.session import create_session_factory

logger = logging.getLogger("distributed_storage.app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(
        level=settings.log_level.value,
        service=settings.service_name,
        env=settings.env.value,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.expected_migration_head = get_expected_head(settings.alembic_config_path)
        logger.info("service_started", extra={"version": __version__})
        try:
            yield
        finally:
            await engine.dispose()
            logger.info("service_stopped")

    app = FastAPI(
        title="Distributed Storage API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )
    app.state.settings = settings
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)
    return app
