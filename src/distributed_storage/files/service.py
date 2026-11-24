"""File metadata and development-only plaintext upload/download (ADR-0009 subset, D14, D18).

Upload protocol (intent first): ``create_file`` writes the file, a ``planned`` version, stripe
and placement in one transaction; ``store_content`` writes the blob outside any transaction and
then commits version, stripe and placement together. A failure between the two leaves the
version ``planned`` and the retry idempotent. Every download is verified against the SHA-256
and length recorded in PostgreSQL before any byte is returned.
"""

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from distributed_storage.api.errors import ApiError, not_found
from distributed_storage.audit.service import AuditAction, AuditEntry, AuditService, Outcome
from distributed_storage.authz.policy import Action, Resource, authorize
from distributed_storage.authz.principal import Principal
from distributed_storage.core.config import Settings
from distributed_storage.db.models import File, FileVersion, ShardPlacement, Stripe
from distributed_storage.files.body import read_limited
from distributed_storage.files.schemas import (
    METADATA_FORMAT_DEV,
    CreatedFileResponse,
    CreateFileRequest,
    FileListResponse,
    FileOut,
    FileSummary,
    StoredResponse,
    VersionOut,
    encode_envelope,
)
from distributed_storage.storage.base import StorageNode
from distributed_storage.storage.errors import (
    BlobConflictError,
    BlobNotFoundError,
    BlobTooLargeError,
    StorageUnavailableError,
)
from distributed_storage.storage.health import NodeState
from distributed_storage.storage.registry import NodeHealthTracker, ensure_local_node

logger = logging.getLogger("distributed_storage.files")

CODEC_NONE = "none"


@dataclass(frozen=True, slots=True)
class ContentResult:
    data: bytes
    sha256_hex: str


def _storage_unavailable() -> ApiError:
    return ApiError(503, "storage_unavailable", "storage is currently unavailable")


def _version_out(version: FileVersion) -> VersionOut:
    return VersionOut(
        id=version.id,
        version_number=version.version_number,
        state=version.state,
        size_bytes=version.size_bytes,
        metadata_format=version.metadata_format,
        metadata_envelope=encode_envelope(version.metadata_envelope),
        created_at=version.created_at,
        committed_at=version.committed_at,
    )


class FileService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        node: StorageNode,
        audit: AuditService,
        tracker: NodeHealthTracker,
    ) -> None:
        self._session = session
        self._settings = settings
        self._node = node
        self._audit = audit
        self._tracker = tracker

    # -- creation ---------------------------------------------------------------------------

    async def create_file(
        self, principal: Principal, request: CreateFileRequest
    ) -> CreatedFileResponse:
        if not authorize(principal, Action.FILE_CREATE, Resource("file", principal.user_id)):
            raise not_found()
        if request.size_bytes > self._settings.max_upload_bytes:
            raise ApiError(
                413,
                "payload_too_large",
                f"files are limited to {self._settings.max_upload_bytes} bytes in this phase",
            )

        node_row = await ensure_local_node(self._session, self._settings)
        if node_row.state in (NodeState.DOWN.value, NodeState.RETIRED.value):
            raise _storage_unavailable()

        file = File(owner_id=principal.user_id)
        self._session.add(file)
        await self._session.flush()
        version = FileVersion(
            file_id=file.id,
            version_number=1,
            state="planned",
            size_bytes=request.size_bytes,
            metadata_format=METADATA_FORMAT_DEV,
            metadata_envelope=request.metadata_envelope,
        )
        self._session.add(version)
        await self._session.flush()
        stripe = Stripe(
            file_version_id=version.id,
            stripe_index=0,
            codec_id=CODEC_NONE,
            data_shards=1,
            parity_shards=0,
            data_length=request.size_bytes,
            padding=0,
            state="planned",
        )
        self._session.add(stripe)
        await self._session.flush()
        self._session.add(
            ShardPlacement(stripe_id=stripe.id, shard_index=0, node_id=node_row.id, state="planned")
        )
        self._audit.add(
            self._session,
            AuditEntry(
                action=AuditAction.FILE_CREATED,
                resource_type="file",
                outcome=Outcome.SUCCESS,
                actor_user_id=principal.user_id,
                device_id=principal.device_id,
                resource_id=str(file.id),
                details={"version_id": str(version.id), "size_bytes": request.size_bytes},
            ),
        )
        await self._session.commit()
        return CreatedFileResponse(
            file_id=file.id,
            version_id=version.id,
            version_number=1,
            size_bytes=request.size_bytes,
            upload_path=f"/v1/files/{file.id}/versions/{version.id}/content",
        )

    # -- content upload ---------------------------------------------------------------------

    async def store_content(
        self,
        principal: Principal,
        file_id: uuid.UUID,
        version_id: uuid.UUID,
        stream: AsyncIterator[bytes],
        content_length: int | None,
    ) -> StoredResponse:
        file = await self._load_owned_file(principal, file_id, Action.FILE_WRITE_CONTENT)
        version = await self._load_version(file.id, version_id)
        if version.state == "deleting":
            raise not_found()
        stripe, placement = await self._load_shard(version.id)
        # Release the read transaction: no database transaction is held open across network or
        # disk I/O (ADR-0004). Loaded objects stay usable (expire_on_commit is off).
        await self._session.commit()

        if content_length is not None:
            if content_length > version.size_bytes:
                raise ApiError(
                    413, "payload_too_large", "the body is larger than the declared size"
                )
            if content_length != version.size_bytes:
                raise ApiError(400, "size_mismatch", "the body is smaller than the declared size")
        data = await read_limited(stream, expected=version.size_bytes)
        digest = hashlib.sha256(data).digest()

        if version.state == "committed":
            return self._idempotent_or_conflict(version, placement, digest)

        try:
            result = await self._node.put(str(placement.id), data)
        except BlobConflictError:
            raise ApiError(
                409, "content_conflict", "different content is already stored for this version"
            ) from None
        except BlobTooLargeError:
            raise ApiError(413, "payload_too_large", "the body exceeds the node limit") from None
        except StorageUnavailableError:
            await self._tracker.observe(False)
            raise _storage_unavailable() from None
        await self._tracker.observe(True)

        if result.sha256 != digest or result.length != len(data):
            await self._integrity_failure(principal, version, placement, "put_result_mismatch")
            raise ApiError(502, "storage_integrity_error", "storage returned an unexpected result")

        locked = await self._session.scalar(
            select(FileVersion)
            .where(FileVersion.id == version.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise not_found()
        await self._session.refresh(placement)
        if locked.state == "committed":  # a concurrent request committed first
            return self._idempotent_or_conflict(locked, placement, digest)

        now = datetime.now(UTC)
        placement.content_hash = digest
        placement.length = len(data)
        placement.state = "stored"
        stripe.state = "stored"
        locked.state = "committed"
        locked.committed_at = now
        file.current_version_id = locked.id
        self._audit.add(
            self._session,
            AuditEntry(
                action=AuditAction.FILE_CONTENT_STORED,
                resource_type="file_version",
                outcome=Outcome.SUCCESS,
                actor_user_id=principal.user_id,
                device_id=principal.device_id,
                resource_id=str(version.id),
                details={"size_bytes": len(data)},
            ),
        )
        await self._session.commit()
        return StoredResponse(
            file_id=file.id,
            version_id=version.id,
            state="committed",
            size_bytes=len(data),
            sha256=digest.hex(),
            idempotent=False,
        )

    @staticmethod
    def _idempotent_or_conflict(
        version: FileVersion, placement: ShardPlacement, digest: bytes
    ) -> StoredResponse:
        if placement.content_hash != digest:
            raise ApiError(
                409, "content_conflict", "different content is already stored for this version"
            )
        return StoredResponse(
            file_id=version.file_id,
            version_id=version.id,
            state="committed",
            size_bytes=version.size_bytes,
            sha256=digest.hex(),
            idempotent=True,
        )

    # -- reads ------------------------------------------------------------------------------

    async def list_files(
        self, principal: Principal, limit: int, after: uuid.UUID | None
    ) -> FileListResponse:
        if not authorize(principal, Action.FILE_LIST, Resource("file", principal.user_id)):
            raise not_found()
        statement = select(File).where(File.owner_id == principal.user_id)
        if after is not None:
            cursor = await self._session.get(File, after)
            if cursor is None or cursor.owner_id != principal.user_id:
                raise ApiError(400, "invalid_cursor", "the cursor is not valid")
            statement = statement.where(
                tuple_(File.created_at, File.id) > tuple_(cursor.created_at, cursor.id)
            )
        files = list(
            await self._session.scalars(
                statement.order_by(File.created_at, File.id).limit(limit + 1)
            )
        )
        has_more = len(files) > limit
        files = files[:limit]

        current_ids = [f.current_version_id for f in files if f.current_version_id is not None]
        versions: dict[uuid.UUID, FileVersion] = {}
        if current_ids:
            rows = await self._session.scalars(
                select(FileVersion).where(FileVersion.id.in_(current_ids))
            )
            versions = {version.id: version for version in rows}
        items = [
            FileSummary(
                id=f.id,
                current_version_id=f.current_version_id,
                created_at=f.created_at,
                current_version=(
                    _version_out(versions[f.current_version_id])
                    if f.current_version_id in versions
                    else None
                ),
            )
            for f in files
        ]
        return FileListResponse(items=items, next_after=files[-1].id if has_more else None)

    async def get_file(self, principal: Principal, file_id: uuid.UUID) -> FileOut:
        file = await self._load_owned_file(principal, file_id, Action.FILE_READ)
        rows = await self._session.scalars(
            select(FileVersion)
            .where(FileVersion.file_id == file.id)
            .order_by(FileVersion.version_number)
        )
        return FileOut(
            id=file.id,
            current_version_id=file.current_version_id,
            created_at=file.created_at,
            versions=[_version_out(version) for version in rows],
        )

    async def read_content(
        self, principal: Principal, file_id: uuid.UUID, version_id: uuid.UUID
    ) -> ContentResult:
        file = await self._load_owned_file(principal, file_id, Action.FILE_READ)
        version = await self._load_version(file.id, version_id)
        if version.state != "committed":
            raise ApiError(409, "not_committed", "this version has no stored content yet")
        _, placement = await self._load_shard(version.id)
        if (
            placement.state != "stored"
            or placement.content_hash is None
            or placement.length is None
        ):
            raise ApiError(409, "not_committed", "this version has no stored content yet")
        await self._session.commit()  # no transaction held open across the blob read

        try:
            data = await self._node.get(str(placement.id))
        except BlobNotFoundError:
            await self._integrity_failure(principal, version, placement, "blob_missing")
            raise ApiError(
                500, "integrity_error", "the stored content failed verification"
            ) from None
        except StorageUnavailableError:
            await self._tracker.observe(False)
            raise _storage_unavailable() from None
        await self._tracker.observe(True)

        digest = hashlib.sha256(data).digest()
        if digest != placement.content_hash or len(data) != placement.length:
            await self._integrity_failure(principal, version, placement, "hash_mismatch")
            raise ApiError(500, "integrity_error", "the stored content failed verification")

        self._audit.add(
            self._session,
            AuditEntry(
                action=AuditAction.FILE_DOWNLOADED,
                resource_type="file_version",
                outcome=Outcome.SUCCESS,
                actor_user_id=principal.user_id,
                device_id=principal.device_id,
                resource_id=str(version.id),
            ),
        )
        await self._session.commit()
        return ContentResult(data=data, sha256_hex=digest.hex())

    # -- helpers ----------------------------------------------------------------------------

    async def _load_owned_file(
        self, principal: Principal, file_id: uuid.UUID, action: Action
    ) -> File:
        file = await self._session.get(File, file_id)
        if file is None:
            raise not_found()
        if not authorize(principal, action, Resource("file", file.owner_id)):
            await self._audit.record_independent(
                AuditEntry(
                    action=AuditAction.AUTHZ_DENIED,
                    resource_type="file",
                    outcome=Outcome.DENIED,
                    actor_user_id=principal.user_id,
                    device_id=principal.device_id,
                    resource_id=str(file_id),
                    details={"action": action.value},
                )
            )
            raise not_found()  # identical to "missing": existence is not revealed
        return file

    async def _load_version(self, file_id: uuid.UUID, version_id: uuid.UUID) -> FileVersion:
        version = await self._session.scalar(
            select(FileVersion).where(FileVersion.id == version_id, FileVersion.file_id == file_id)
        )
        if version is None:
            raise not_found()
        return version

    async def _load_shard(self, version_id: uuid.UUID) -> tuple[Stripe, ShardPlacement]:
        stripe = await self._session.scalar(
            select(Stripe).where(Stripe.file_version_id == version_id, Stripe.stripe_index == 0)
        )
        if stripe is None:
            raise RuntimeError("file version has no stripe")
        placement = await self._session.scalar(
            select(ShardPlacement).where(
                ShardPlacement.stripe_id == stripe.id, ShardPlacement.shard_index == 0
            )
        )
        if placement is None:
            raise RuntimeError("stripe has no shard placement")
        return stripe, placement

    async def _integrity_failure(
        self,
        principal: Principal,
        version: FileVersion,
        placement: ShardPlacement,
        reason: str,
    ) -> None:
        logger.error(
            "integrity_check_failed",
            extra={"version_id": str(version.id), "shard_id": str(placement.id), "reason": reason},
        )
        await self._audit.record_independent(
            AuditEntry(
                action=AuditAction.INTEGRITY_MISMATCH,
                resource_type="file_version",
                outcome=Outcome.FAILURE,
                actor_user_id=principal.user_id,
                device_id=principal.device_id,
                resource_id=str(version.id),
                details={"reason": reason, "shard_id": str(placement.id)},
            )
        )
