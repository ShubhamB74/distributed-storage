"""The StorageNode contract (ADR-0002, ADR-0014).

A storage node is an independent, dumb blob store. It never replicates, erasure-codes or
interprets data: redundancy, placement, health policy and integrity decisions belong to the
coordinator. Blobs are keyed by the shard placement's UUID and are write-once.

Contract for every adapter:

- ``put`` is durable when it returns: the bytes survive a crash of the node process.
- ``put`` never overwrites. The same bytes under an existing key is a no-op success
  (``created=False``); different bytes raise ``BlobConflictError``.
- ``put`` returns the length and SHA-256 the node computed, so the caller can compare them
  with its own record.
- ``get`` returns exactly the stored bytes and does not verify them: callers verify against
  the SHA-256 recorded in PostgreSQL, which is authoritative.
- ``delete`` is idempotent.
"""

import re
from dataclasses import dataclass
from typing import Protocol

from distributed_storage.storage.errors import InvalidBlobKeyError

_KEY_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def validate_blob_key(key: str) -> str:
    """Return ``key`` if it is a canonical lowercase UUID, else raise.

    Keys become file names or object names, so anything else (path separators, dots,
    uppercase variants that collide on case-insensitive file systems) is rejected.
    """
    if _KEY_PATTERN.fullmatch(key) is None:
        raise InvalidBlobKeyError("blob keys must be canonical lowercase UUIDs")
    return key


@dataclass(frozen=True, slots=True)
class PutResult:
    length: int
    sha256: bytes
    created: bool


@dataclass(frozen=True, slots=True)
class BlobInfo:
    length: int


@dataclass(frozen=True, slots=True)
class NodeHealth:
    healthy: bool
    detail: str
    free_bytes: int | None = None


class StorageNode(Protocol):
    async def put(self, key: str, data: bytes) -> PutResult: ...

    async def get(self, key: str) -> bytes: ...

    async def head(self, key: str) -> BlobInfo | None: ...

    async def delete(self, key: str) -> bool: ...

    async def health(self) -> NodeHealth: ...
