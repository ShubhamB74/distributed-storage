from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from distributed_storage.api.main import create_app
from distributed_storage.core.config import Settings
from distributed_storage.db.engine import create_engine
from tests.integration.api.helpers import Api

REPO_ROOT = Path(__file__).resolve().parents[3]

ApiFactory = Callable[..., AbstractAsyncContextManager[Api]]


@pytest.fixture
def api_factory(migrated_database: Settings, tmp_path: Path) -> ApiFactory:
    """Build an API against a freshly migrated database; keyword arguments override settings."""

    @asynccontextmanager
    async def make(**overrides: Any) -> AsyncIterator[Api]:
        values: dict[str, Any] = {
            "alembic_config_path": REPO_ROOT / "alembic.ini",
            "blob_root": tmp_path / "blobs",
            "allow_registration": True,
            "allow_dev_plaintext_upload": True,
            "max_upload_bytes": 64 * 1024,
            # Minimal Argon2 cost keeps the tests fast; production defaults live in Settings.
            "argon2_time_cost": 1,
            "argon2_memory_cost_kib": 8,
            "argon2_parallelism": 1,
            "login_max_failures": 3,
            "login_lockout_base_seconds": 60,
        }
        values.update(overrides)
        settings = migrated_database.model_copy(update=values)
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                engine = create_engine(settings)
                try:
                    yield Api(client=client, app=app, settings=settings, engine=engine)
                finally:
                    await engine.dispose()

    return make


@pytest_asyncio.fixture
async def api(api_factory: ApiFactory) -> AsyncIterator[Api]:
    async with api_factory() as instance:
        yield instance
