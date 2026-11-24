"""Shared helpers for API integration tests (imported as tests.integration.api.helpers)."""

import base64
import json
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from distributed_storage.core.config import Settings
from distributed_storage.storage.base import BlobInfo, NodeHealth, PutResult
from distributed_storage.storage.errors import StorageUnavailableError
from distributed_storage.storage.local import LocalBlobStorage

SECRET = "integration-test-auth-secret-0123456789"


def envelope(name: str = "note.txt") -> str:
    return base64.b64encode(json.dumps({"name": name}).encode()).decode()


@dataclass
class Api:
    client: httpx.AsyncClient
    app: FastAPI
    settings: Settings
    engine: AsyncEngine

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def register(
        self, email: str = "alice@example.com", secret: str = SECRET
    ) -> httpx.Response:
        return await self.client.post(
            "/v1/auth/register", json={"email": email, "auth_secret": secret}
        )

    async def login(
        self, email: str = "alice@example.com", secret: str = SECRET, device: str = "laptop"
    ) -> httpx.Response:
        return await self.client.post(
            "/v1/auth/login",
            json={"email": email, "auth_secret": secret, "device_name": device},
        )

    async def user_token(self, name: str = "alice", device: str = "laptop") -> str:
        """Register ``name@example.com`` (if new) and log in; returns the bearer token."""
        email = f"{name}@example.com"
        registered = await self.register(email)
        assert registered.status_code in (201, 409), registered.text
        response = await self.login(email, device=device)
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        assert isinstance(token, str)
        return token

    async def create_file(self, token: str, size: int, name: str = "note.txt") -> httpx.Response:
        return await self.client.post(
            "/v1/files",
            headers=self.auth(token),
            json={
                "metadata_format": "dev-plain-v0",
                "metadata_envelope": envelope(name),
                "size_bytes": size,
            },
        )

    async def put_content(self, token: str, upload_path: str, data: bytes) -> httpx.Response:
        return await self.client.put(upload_path, headers=self.auth(token), content=data)

    async def upload(self, token: str, data: bytes, name: str = "note.txt") -> tuple[str, str]:
        """Create and upload a file; returns (file_id, version_id)."""
        created = await self.create_file(token, len(data), name)
        assert created.status_code == 201, created.text
        body = created.json()
        stored = await self.put_content(token, body["upload_path"], data)
        assert stored.status_code == 200, stored.text
        return str(body["file_id"]), str(body["version_id"])

    async def sql(self, statement: str, **params: Any) -> list[tuple[Any, ...]]:
        async with self.engine.begin() as connection:
            result = await connection.execute(text(statement), params)
            return [tuple(row) for row in result] if result.returns_rows else []

    async def audit(self, action: str | None = None) -> list[tuple[Any, ...]]:
        """(action, outcome, actor_user_id, resource_id, details, request_id), oldest first."""
        columns = "action, outcome, actor_user_id, resource_id, details, request_id"
        if action is None:
            rows = await self.sql(f"SELECT {columns} FROM audit_events ORDER BY id")  # noqa: S608
        else:
            rows = await self.sql(
                f"SELECT {columns} FROM audit_events WHERE action = :action ORDER BY id",  # noqa: S608
                action=action,
            )
        # Raw text() queries may return JSONB as a string depending on the driver codecs.
        return [
            (*row[:4], json.loads(row[4]) if isinstance(row[4], str) else row[4], row[5])
            for row in rows
        ]


class FlakyNode:
    """Wraps a real node and fails operations on demand (fault injection)."""

    def __init__(self, inner: LocalBlobStorage) -> None:
        self.inner = inner
        self.fail_puts = 0
        self.fail_gets = 0

    async def put(self, key: str, data: bytes) -> PutResult:
        if self.fail_puts > 0:
            self.fail_puts -= 1
            raise StorageUnavailableError("simulated outage")
        return await self.inner.put(key, data)

    async def get(self, key: str) -> bytes:
        if self.fail_gets > 0:
            self.fail_gets -= 1
            raise StorageUnavailableError("simulated outage")
        return await self.inner.get(key)

    async def head(self, key: str) -> BlobInfo | None:
        return await self.inner.head(key)

    async def delete(self, key: str) -> bool:
        return await self.inner.delete(key)

    async def health(self) -> NodeHealth:
        return await self.inner.health()

    async def sweep_tmp(self, older_than_seconds: float) -> int:
        return await self.inner.sweep_tmp(older_than_seconds)
