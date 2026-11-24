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
from distributed_storage.api.errors import install_error_handlers
from distributed_storage.api.health import router as health_router
from distributed_storage.api.middleware import RequestContextMiddleware
from distributed_storage.audit.service import AuditService
from distributed_storage.auth.passwords import PasswordVerifier
from distributed_storage.auth.routes import router as auth_router
from distributed_storage.core.config import Settings, get_settings
from distributed_storage.core.logging import configure_logging
from distributed_storage.db.engine import create_engine
from distributed_storage.db.migrations import get_expected_head
from distributed_storage.db.session import create_session_factory
from distributed_storage.devices.routes import router as devices_router
from distributed_storage.files.routes import router as files_router
from distributed_storage.storage.errors import StorageError
from distributed_storage.storage.local import LocalBlobStorage
from distributed_storage.storage.registry import (
    NodeHealthTracker,
    ensure_local_node,
    thresholds_from,
)

logger = logging.getLogger("distributed_storage.app")

TEMP_FILE_MAX_AGE_SECONDS = 3600


async def _startup_housekeeping(app: FastAPI, settings: Settings) -> None:
    """Best effort: the API must start even if PostgreSQL or the blob root is briefly unavailable
    (readiness reports the truth). File operations re-register the node on demand."""
    try:
        async with app.state.session_factory() as session:
            await ensure_local_node(session, settings)
            await session.commit()
    except Exception:
        logger.warning("node_registration_deferred", exc_info=True)
    try:
        removed = await app.state.storage_node.sweep_tmp(TEMP_FILE_MAX_AGE_SECONDS)
        if removed:
            logger.info("stale_temp_files_removed", extra={"count": removed})
    except StorageError:
        logger.warning("temp_file_sweep_failed", exc_info=True)


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
        session_factory = create_session_factory(engine)
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.expected_migration_head = get_expected_head(settings.alembic_config_path)
        app.state.password_verifier = PasswordVerifier(
            time_cost=settings.argon2_time_cost,
            memory_cost_kib=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
        )
        app.state.audit = AuditService(session_factory)
        app.state.storage_node = LocalBlobStorage(settings.blob_root)
        app.state.health_tracker = NodeHealthTracker(
            session_factory, settings.local_node_name, thresholds_from(settings)
        )
        await _startup_housekeeping(app, settings)
        if settings.allow_dev_plaintext_upload:
            logger.warning(
                "dev_plaintext_upload_enabled",
                extra={"note": "files are stored unencrypted: development only"},
            )
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
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(devices_router)
    app.include_router(files_router)
    return app
