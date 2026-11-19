import logging
import re
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from distributed_storage.api.middleware import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
)


async def _ok(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = Starlette(routes=[Route("/", _ok)])
    app.add_middleware(RequestContextMiddleware)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


async def test_request_id_is_generated_and_unique(client: httpx.AsyncClient) -> None:
    first = await client.get("/")
    second = await client.get("/")
    assert re.fullmatch(r"[0-9a-f]{32}", first.headers[REQUEST_ID_HEADER])
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


async def test_client_cannot_choose_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/", headers={REQUEST_ID_HEADER: "attacker-chosen"})
    assert response.headers[REQUEST_ID_HEADER] != "attacker-chosen"


async def test_valid_correlation_id_is_propagated(client: httpx.AsyncClient) -> None:
    response = await client.get("/", headers={CORRELATION_ID_HEADER: "trace-123.abc_X"})
    assert response.headers[CORRELATION_ID_HEADER] == "trace-123.abc_X"


@pytest.mark.parametrize("bad", ["has spaces", "x" * 65, "semi;colon", 'quote"'])
async def test_invalid_correlation_id_is_replaced(client: httpx.AsyncClient, bad: str) -> None:
    response = await client.get("/", headers={CORRELATION_ID_HEADER: bad})
    assert response.headers[CORRELATION_ID_HEADER] == response.headers[REQUEST_ID_HEADER]


async def test_correlation_id_defaults_to_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.headers[CORRELATION_ID_HEADER] == response.headers[REQUEST_ID_HEADER]


async def test_access_log_has_status_and_omits_query_string(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="distributed_storage.http"):
        await client.get("/?token=supersecret")
    records = [r for r in caplog.records if r.name == "distributed_storage.http"]
    assert len(records) == 1
    record = records[0]
    assert record.getMessage() == "http_request_completed"
    assert record.__dict__["status_code"] == 200
    assert record.__dict__["path"] == "/"
    assert "supersecret" not in str(record.__dict__)
