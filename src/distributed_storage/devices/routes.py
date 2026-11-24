import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from distributed_storage.api.dependencies import SessionDep
from distributed_storage.audit.service import AuditService
from distributed_storage.auth.dependencies import PrincipalDep
from distributed_storage.devices.schemas import DeviceOut
from distributed_storage.devices.service import DeviceService

router = APIRouter(prefix="/v1/devices", tags=["devices"])


def get_device_service(request: Request, session: SessionDep) -> DeviceService:
    audit: AuditService = request.app.state.audit
    return DeviceService(session=session, audit=audit)


DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]


@router.get("")
async def list_devices(principal: PrincipalDep, service: DeviceServiceDep) -> list[DeviceOut]:
    devices = await service.list_devices(principal)
    return [
        DeviceOut(
            id=device.id,
            name=device.name,
            created_at=device.created_at,
            last_seen_at=device.last_seen_at,
            revoked_at=device.revoked_at,
            is_current=device.id == principal.device_id,
        )
        for device in devices
    ]


@router.delete("/{device_id}", status_code=204)
async def revoke_device(
    device_id: uuid.UUID, principal: PrincipalDep, service: DeviceServiceDep
) -> Response:
    await service.revoke(principal, device_id)
    return Response(status_code=204)
