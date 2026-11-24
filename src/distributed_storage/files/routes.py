import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from distributed_storage.api.dependencies import (
    DEV_ONLY_HEADER,
    DEV_ONLY_VALUE,
    SessionDep,
    SettingsDep,
    require_dev_plaintext,
)
from distributed_storage.api.errors import ApiError
from distributed_storage.audit.service import AuditService
from distributed_storage.auth.dependencies import PrincipalDep
from distributed_storage.files.schemas import (
    CreatedFileResponse,
    CreateFileRequest,
    FileListResponse,
    FileOut,
    StoredResponse,
)
from distributed_storage.files.service import FileService
from distributed_storage.storage.base import StorageNode
from distributed_storage.storage.registry import NodeHealthTracker

router = APIRouter(
    prefix="/v1/files",
    tags=["files (development-only plaintext)"],
    dependencies=[Depends(require_dev_plaintext)],
)


def get_file_service(request: Request, session: SessionDep, settings: SettingsDep) -> FileService:
    state = request.app.state
    node: StorageNode = state.storage_node
    audit: AuditService = state.audit
    tracker: NodeHealthTracker = state.health_tracker
    return FileService(session=session, settings=settings, node=node, audit=audit, tracker=tracker)


FileServiceDep = Annotated[FileService, Depends(get_file_service)]


@router.post("", status_code=201)
async def create_file(
    body: CreateFileRequest, principal: PrincipalDep, service: FileServiceDep
) -> CreatedFileResponse:
    return await service.create_file(principal, body)


@router.put("/{file_id}/versions/{version_id}/content")
async def put_content(
    file_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
    principal: PrincipalDep,
    service: FileServiceDep,
) -> StoredResponse:
    header = request.headers.get("content-length")
    content_length: int | None = None
    if header is not None:
        try:
            content_length = int(header)
        except ValueError:
            raise ApiError(400, "invalid_content_length", "invalid Content-Length") from None
    return await service.store_content(
        principal, file_id, version_id, request.stream(), content_length
    )


@router.get("")
async def list_files(
    principal: PrincipalDep,
    service: FileServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: uuid.UUID | None = None,
) -> FileListResponse:
    return await service.list_files(principal, limit, after)


@router.get("/{file_id}")
async def get_file(file_id: uuid.UUID, principal: PrincipalDep, service: FileServiceDep) -> FileOut:
    return await service.get_file(principal, file_id)


@router.get("/{file_id}/versions/{version_id}/content")
async def get_content(
    file_id: uuid.UUID,
    version_id: uuid.UUID,
    principal: PrincipalDep,
    service: FileServiceDep,
) -> Response:
    result = await service.read_content(principal, file_id, version_id)
    return Response(
        content=result.data,
        media_type="application/octet-stream",
        headers={
            "X-Content-SHA256": result.sha256_hex,
            "Cache-Control": "no-store",
            DEV_ONLY_HEADER: DEV_ONLY_VALUE,
        },
    )
