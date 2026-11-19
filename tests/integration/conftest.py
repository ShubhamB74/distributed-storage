"""Integration fixtures: real PostgreSQL only (never SQLite).

Each test gets its own throwaway database (CREATE DATABASE, dropped afterwards), so tests
are isolated from each other and never touch the development database.

If PostgreSQL is not reachable: locally the tests are skipped with instructions; when the
CI environment variable is set they FAIL, so a misconfigured pipeline can never go green
by silently skipping everything.
"""

import asyncio
import os
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import NoReturn

import asyncpg
import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError

from distributed_storage.api.main import create_app
from distributed_storage.core.config import Environment, Settings

REPO_ROOT = Path(__file__).resolve().parents[2]

DatabaseFactory = Callable[[], Awaitable[Settings]]
ApiClientFactory = Callable[[Settings], AbstractAsyncContextManager[httpx.AsyncClient]]


def unavailable(reason: str) -> NoReturn:
    if os.environ.get("CI"):
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def base_settings() -> Settings:
    try:
        loaded = Settings.load()
    except ValidationError as exc:
        unavailable(
            f"database settings not configured ({exc.error_count()} error(s)). "
            "Run ./scripts/gen-dev-env.sh and `make db-up`."
        )
    return loaded.model_copy(update={"env": Environment.TEST})


async def _admin_execute(settings: Settings, statement: str) -> None:
    connection = await asyncpg.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
        database="postgres",
        timeout=settings.db_connect_timeout,
    )
    try:
        await connection.execute(statement)
    finally:
        await connection.close()


@pytest_asyncio.fixture
async def database_factory(base_settings: Settings) -> AsyncIterator[DatabaseFactory]:
    created: list[str] = []

    async def create() -> Settings:
        name = f"distributed_storage_test_{uuid.uuid4().hex[:12]}"
        try:
            await _admin_execute(base_settings, f'CREATE DATABASE "{name}"')
        except (OSError, asyncpg.PostgresError, TimeoutError) as exc:
            unavailable(f"PostgreSQL not reachable ({type(exc).__name__}). Run `make db-up`.")
        created.append(name)
        return base_settings.with_database(name)

    yield create

    for name in created:
        await _admin_execute(base_settings, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest_asyncio.fixture
async def temp_database(database_factory: DatabaseFactory) -> Settings:
    """An empty, isolated database (no migrations applied)."""
    return await database_factory()


async def run_alembic(settings: Settings, *args: str) -> tuple[int, str, str]:
    """Run Alembic in a subprocess (its async env uses asyncio.run, so not in-process)."""
    env = {
        **os.environ,
        "DISTRIBUTED_STORAGE_ENV": settings.env.value,
        "DISTRIBUTED_STORAGE_DB_HOST": settings.db_host,
        "DISTRIBUTED_STORAGE_DB_PORT": str(settings.db_port),
        "DISTRIBUTED_STORAGE_DB_NAME": settings.db_name,
        "DISTRIBUTED_STORAGE_DB_USER": settings.db_user,
        "DISTRIBUTED_STORAGE_DB_PASSWORD": settings.db_password.get_secret_value(),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        *args,
        cwd=REPO_ROOT,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return process.returncode or 0, stdout.decode(), stderr.decode()


@pytest.fixture
def alembic() -> Callable[..., Awaitable[tuple[int, str, str]]]:
    return run_alembic


@pytest_asyncio.fixture
async def migrated_database(temp_database: Settings) -> Settings:
    code, _, err = await run_alembic(temp_database, "upgrade", "head")
    assert code == 0, err
    return temp_database


@pytest.fixture
def api_client() -> ApiClientFactory:
    @asynccontextmanager
    async def make(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
        app = create_app(
            settings.model_copy(update={"alembic_config_path": REPO_ROOT / "alembic.ini"})
        )
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            yield client

    return make
