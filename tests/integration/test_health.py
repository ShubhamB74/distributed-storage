import socket
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import httpx

from distributed_storage.core.config import Settings

ApiClientFactory = Callable[[Settings], AbstractAsyncContextManager[httpx.AsyncClient]]


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def test_readyz_is_ok_when_database_is_migrated(
    migrated_database: Settings, api_client: ApiClientFactory
) -> None:
    async with api_client(migrated_database) as client:
        response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "migrations": "ok"},
    }


async def test_readyz_is_503_when_schema_is_not_migrated(
    temp_database: Settings, api_client: ApiClientFactory
) -> None:
    async with api_client(temp_database) as client:
        response = await client.get("/readyz")
        liveness = await client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "migrations": "fail"}
    assert liveness.status_code == 200


async def test_readyz_is_503_when_database_is_unreachable(
    temp_database: Settings, api_client: ApiClientFactory
) -> None:
    unreachable = temp_database.model_copy(update={"db_port": _unused_port()})
    started = time.monotonic()
    async with api_client(unreachable) as client:
        response = await client.get("/readyz")
        liveness = await client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "fail", "migrations": "fail"}
    assert liveness.status_code == 200
    assert time.monotonic() - started < 10


async def test_readyz_response_leaks_no_internals(
    temp_database: Settings, api_client: ApiClientFactory
) -> None:
    unreachable = temp_database.model_copy(update={"db_port": _unused_port()})
    async with api_client(unreachable) as client:
        response = await client.get("/readyz")
    body = response.text
    assert set(response.json()) == {"status", "checks"}
    assert temp_database.db_password.get_secret_value() not in body
    assert temp_database.db_user not in body
    assert "Traceback" not in body
