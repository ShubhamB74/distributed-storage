from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from fastapi import FastAPI
from pydantic import BaseModel, Field

from distributed_storage.api.errors import ApiError, install_error_handlers
from distributed_storage.api.middleware import RequestContextMiddleware


class Body(BaseModel):
    auth_secret: str = Field(min_length=16)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    @app.get("/api-error")
    async def api_error() -> None:
        raise ApiError(418, "teapot", "short and stout", headers={"X-Extra": "1"})

    @app.post("/validate")
    async def validate(body: Body) -> None:
        return None

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_api_errors_use_the_uniform_body_with_a_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/api-error")
    assert response.status_code == 418
    assert response.headers["x-extra"] == "1"
    error = response.json()["error"]
    assert error["code"] == "teapot"
    assert error["message"] == "short and stout"
    assert error["request_id"] == response.headers["x-request-id"]


async def test_validation_errors_never_echo_the_submitted_input(client: httpx.AsyncClient) -> None:
    response = await client.post("/validate", json={"auth_secret": "hunter2-short"})
    assert response.status_code == 422
    assert "hunter2-short" not in response.text
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["location"] == ["body", "auth_secret"]


async def test_unknown_routes_use_the_uniform_body(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"


async def test_unhandled_exceptions_return_a_generic_500(client: httpx.AsyncClient) -> None:
    response = await client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.text
