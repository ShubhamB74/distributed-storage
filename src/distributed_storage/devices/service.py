"""Device listing and revocation (D17 identity model; keys arrive in Phase 2)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from distributed_storage.api.errors import not_found
from distributed_storage.audit.service import AuditAction, AuditEntry, AuditService, Outcome
from distributed_storage.authz.policy import Action, Resource, authorize
from distributed_storage.authz.principal import Principal
from distributed_storage.db.models import Device
from distributed_storage.db.models import Session as SessionModel


class DeviceService:
    def __init__(self, *, session: AsyncSession, audit: AuditService) -> None:
        self._session = session
        self._audit = audit

    async def list_devices(self, principal: Principal) -> list[Device]:
        if not authorize(principal, Action.DEVICE_LIST, Resource("device", principal.user_id)):
            raise not_found()
        rows = await self._session.scalars(
            select(Device)
            .where(Device.user_id == principal.user_id)
            .order_by(Device.created_at, Device.id)
        )
        return list(rows)

    async def revoke(self, principal: Principal, device_id: uuid.UUID) -> None:
        """Revoke a device and every session bound to it. Idempotent."""
        device = await self._session.get(Device, device_id)
        if device is None:
            raise not_found()
        if not authorize(principal, Action.DEVICE_REVOKE, Resource("device", device.user_id)):
            await self._audit.record_independent(
                AuditEntry(
                    action=AuditAction.AUTHZ_DENIED,
                    resource_type="device",
                    outcome=Outcome.DENIED,
                    actor_user_id=principal.user_id,
                    device_id=principal.device_id,
                    resource_id=str(device_id),
                    details={"action": Action.DEVICE_REVOKE.value},
                )
            )
            raise not_found()

        if device.revoked_at is None:
            now = datetime.now(UTC)
            device.revoked_at = now
            await self._session.execute(
                update(SessionModel)
                .where(SessionModel.device_id == device_id, SessionModel.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            self._audit.add(
                self._session,
                AuditEntry(
                    action=AuditAction.DEVICE_REVOKED,
                    resource_type="device",
                    outcome=Outcome.SUCCESS,
                    actor_user_id=principal.user_id,
                    device_id=principal.device_id,
                    resource_id=str(device_id),
                ),
            )
        await self._session.commit()
