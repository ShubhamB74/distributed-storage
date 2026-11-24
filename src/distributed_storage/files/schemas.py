import base64
import binascii
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

METADATA_FORMAT_DEV = "dev-plain-v0"
MAX_METADATA_BYTES = 65536


def _decode_base64(value: object) -> bytes:
    if not isinstance(value, str):
        raise ValueError("must be a base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("must be valid base64") from None


Base64Bytes = Annotated[bytes, BeforeValidator(_decode_base64)]


class CreateFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata_format: Literal["dev-plain-v0"]
    # Opaque to the server: Phase 1 stores development-only plaintext JSON here.
    metadata_envelope: Base64Bytes = Field(min_length=1, max_length=MAX_METADATA_BYTES)
    size_bytes: int = Field(ge=1)


class CreatedFileResponse(BaseModel):
    file_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    size_bytes: int
    upload_path: str


class VersionOut(BaseModel):
    id: uuid.UUID
    version_number: int
    state: str
    size_bytes: int
    metadata_format: str
    metadata_envelope: str
    created_at: datetime
    committed_at: datetime | None


class FileOut(BaseModel):
    id: uuid.UUID
    current_version_id: uuid.UUID | None
    created_at: datetime
    versions: list[VersionOut]


class FileSummary(BaseModel):
    id: uuid.UUID
    current_version_id: uuid.UUID | None
    created_at: datetime
    current_version: VersionOut | None


class FileListResponse(BaseModel):
    items: list[FileSummary]
    next_after: uuid.UUID | None


class StoredResponse(BaseModel):
    file_id: uuid.UUID
    version_id: uuid.UUID
    state: str
    size_bytes: int
    sha256: str
    idempotent: bool


def encode_envelope(envelope: bytes) -> str:
    return base64.b64encode(envelope).decode("ascii")
