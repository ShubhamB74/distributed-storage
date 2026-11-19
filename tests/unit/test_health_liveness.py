from collections.abc import AsyncIterator

import httpx
import pytest_asyncio

from distributed_storage.api.main import create_app
from distributed_storage.core.config import Environment, Settings


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    # Lifespan is deliberately not started: liveness must not depend on any resource.
    app = create_app(settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


async def test_healthz_is_ok_without_any_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "x-request-id" in response.headers


async def test_docs_hidden_in_prod(settings: Settings) -> None:
    prod = settings.model_copy(update={"env": Environment.PROD})
    app = create_app(prod)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        assert (await http_client.get("/docs")).status_code == 404
        assert (await http_client.get("/openapi.json")).status_code == 404
