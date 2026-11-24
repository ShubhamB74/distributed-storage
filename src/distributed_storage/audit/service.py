"""Append-only audit events (table enforced by triggers; hash chaining arrives in Phase 7).

Success events are added to the caller's transaction so they commit or roll back with the
action. Denials and failures are written in their own transaction so a rolled-back request
still leaves a trace. Event details must never contain secrets, keys, tokens or email
addresses; they pass through the log redaction as a safety net.
"""

import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from distributed_storage.core.logging import redact, request_id_var
from distributed_storage.db.models import AuditEvent

logger = logging.getLogger("distributed_storage.audit")


class AuditAction:
    USER_REGISTERED = "user.registered"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    DEVICE_REVOKED = "device.revoked"
    FILE_CREATED = "file.created"
    FILE_CONTENT_STORED = "file.content_stored"
    FILE_DOWNLOADED = "file.downloaded"
    AUTHZ_DENIED = "authz.denied"
    INTEGRITY_MISMATCH = "integrity.mismatch"


class Outcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    action: str
    resource_type: str
    outcome: Outcome
    actor_user_id: uuid.UUID | None = None
    device_id: uuid.UUID | None = None
    resource_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class AuditService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def add(session: AsyncSession, entry: AuditEntry) -> None:
        """Add the event to the caller's transaction (the caller commits)."""
        session.add(
            AuditEvent(
                action=entry.action,
                resource_type=entry.resource_type,
                outcome=entry.outcome.value,
                actor_user_id=entry.actor_user_id,
                device_id=entry.device_id,
                resource_id=entry.resource_id,
                request_id=request_id_var.get(),
                details=redact(entry.details),
            )
        )

    async def record_independent(self, entry: AuditEntry) -> None:
        """Write the event in its own transaction. Never raises: auditing must not mask the
        outcome of the request that triggered it."""
        try:
            async with self._session_factory() as session:
                self.add(session, entry)
                await session.commit()
        except Exception:
            logger.error("audit_write_failed", exc_info=True)
