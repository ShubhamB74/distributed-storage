"""Liveness and readiness endpoints.

- ``/healthz``: the process is up. No dependencies, so it never flaps with the database.
- ``/readyz``: the service can do useful work: PostgreSQL reachable AND the schema is at
  the expected migration head. Failures return 503 with coarse check names only.
"""

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(tags=["health"])
logger = logging.getLogger("distributed_storage.health")


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def _check_database(engine: AsyncEngine, timeout_seconds: float) -> bool:
    try:
        async with asyncio.timeout(timeout_seconds), engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.warning("readiness_database_check_failed", exc_info=True)
        return False
    return True


async def _check_migrations(
    engine: AsyncEngine, expected_head: str, timeout_seconds: float
) -> bool:
    try:
        async with asyncio.timeout(timeout_seconds), engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current = result.scalar_one_or_none()
    except Exception:
        logger.warning("readiness_migration_check_failed", exc_info=True)
        return False
    if current != expected_head:
        logger.warning(
            "readiness_migration_mismatch",
            extra={"current": current, "expected": expected_head},
        )
        return False
    return True


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    engine: AsyncEngine = request.app.state.engine
    expected_head: str = request.app.state.expected_migration_head
    timeout: float = request.app.state.settings.readiness_timeout

    database_ok = await _check_database(engine, timeout)
    migrations_ok = database_ok and await _check_migrations(engine, expected_head, timeout)

    checks = {
        "database": "ok" if database_ok else "fail",
        "migrations": "ok" if migrations_ok else "fail",
    }
    ready = database_ok and migrations_ok
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "unavailable", "checks": checks},
    )
