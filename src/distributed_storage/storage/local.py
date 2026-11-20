"""Filesystem-backed StorageNode for development, tests and single-host deployments.

Durability: a successful ``put`` means the bytes were written to a temporary file, flushed and
fsynced, then published under their final name with ``os.link`` (atomic and refuses to
overwrite), and, on POSIX, the directory entry was fsynced. A crash at any point leaves either
no blob or a complete blob; leftover temporary files are invisible and removed by
``sweep_tmp``. The file system must support hard links.

Limits: on Windows the directory fsync is skipped, and whether the OS honours fsync cannot be
verified remotely (ADR-0008). Blocking I/O runs in worker threads.
"""

import asyncio
import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path

from distributed_storage.storage.base import BlobInfo, NodeHealth, PutResult, validate_blob_key
from distributed_storage.storage.errors import (
    BlobConflictError,
    BlobNotFoundError,
    BlobTooLargeError,
    StorageUnavailableError,
)

DEFAULT_MAX_BLOB_BYTES = 64 * 1024 * 1024
_READ_CHUNK = 1024 * 1024


def _hash_file(path: Path) -> tuple[bytes, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while chunk := handle.read(_READ_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.digest(), size


class LocalBlobStorage:
    def __init__(self, root: Path, *, max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES) -> None:
        self._root = root
        self._blob_dir = root / "blobs"
        self._tmp_dir = root / ".tmp"
        self._max_blob_bytes = max_blob_bytes

    @property
    def root(self) -> Path:
        return self._root

    @property
    def tmp_dir(self) -> Path:
        return self._tmp_dir

    def _blob_path(self, key: str) -> Path:
        return self._blob_dir / key[:2] / key

    # Steps of the write path are separate methods so crash and I/O failures can be injected.
    def _write_temp(self, tmp: Path, data: bytes) -> None:
        def opener(path: str, flags: int) -> int:
            return os.open(path, flags, 0o600)

        with open(tmp, "xb", opener=opener) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def _publish(self, tmp: Path, final: Path) -> None:
        os.link(tmp, final)  # raises FileExistsError if final exists: atomic, never overwrites

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        if os.name != "posix":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _put_sync(self, key: str, data: bytes) -> PutResult:
        validate_blob_key(key)
        if len(data) > self._max_blob_bytes:
            raise BlobTooLargeError(f"blob exceeds the node limit of {self._max_blob_bytes} bytes")
        digest = hashlib.sha256(data).digest()
        final = self._blob_path(key)
        tmp = self._tmp_dir / f"{key}.{uuid.uuid4().hex}.tmp"
        try:
            final.parent.mkdir(parents=True, exist_ok=True)
            self._tmp_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._write_temp(tmp, data)
                try:
                    self._publish(tmp, final)
                except FileExistsError:
                    return self._existing_result(key, final, digest, len(data))
            finally:
                tmp.unlink(missing_ok=True)
            self._fsync_dir(final.parent)
        except OSError as exc:
            raise StorageUnavailableError(f"storage I/O failed: {type(exc).__name__}") from exc
        return PutResult(length=len(data), sha256=digest, created=True)

    @staticmethod
    def _existing_result(key: str, final: Path, digest: bytes, length: int) -> PutResult:
        existing_digest, existing_length = _hash_file(final)
        if existing_digest == digest and existing_length == length:
            return PutResult(length=length, sha256=digest, created=False)
        raise BlobConflictError(f"blob {key} already exists with different content")

    def _get_sync(self, key: str) -> bytes:
        validate_blob_key(key)
        path = self._blob_path(key)
        try:
            if path.stat().st_size > self._max_blob_bytes:
                raise BlobTooLargeError(
                    f"blob exceeds the node limit of {self._max_blob_bytes} bytes"
                )
            return path.read_bytes()
        except FileNotFoundError:
            raise BlobNotFoundError(key) from None
        except OSError as exc:
            raise StorageUnavailableError(f"storage I/O failed: {type(exc).__name__}") from exc

    def _head_sync(self, key: str) -> BlobInfo | None:
        validate_blob_key(key)
        try:
            return BlobInfo(length=self._blob_path(key).stat().st_size)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StorageUnavailableError(f"storage I/O failed: {type(exc).__name__}") from exc

    def _delete_sync(self, key: str) -> bool:
        validate_blob_key(key)
        try:
            self._blob_path(key).unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise StorageUnavailableError(f"storage I/O failed: {type(exc).__name__}") from exc
        return True

    def _health_sync(self) -> NodeHealth:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            probe = self._root / f".health-{uuid.uuid4().hex}"
            with open(probe, "xb") as handle:
                handle.write(b"ok")
                handle.flush()
                os.fsync(handle.fileno())
            probe.unlink()
            free_bytes = shutil.disk_usage(self._root).free
            return NodeHealth(healthy=True, detail="ok", free_bytes=free_bytes)
        except OSError as exc:
            return NodeHealth(healthy=False, detail=f"{type(exc).__name__}")

    def _sweep_tmp_sync(self, older_than_seconds: float) -> int:
        if not self._tmp_dir.is_dir():
            return 0
        cutoff = time.time() - older_than_seconds
        removed = 0
        try:
            for entry in self._tmp_dir.iterdir():
                try:
                    if entry.is_file() and entry.stat().st_mtime <= cutoff:
                        entry.unlink()
                        removed += 1
                except FileNotFoundError:
                    continue
        except OSError as exc:
            raise StorageUnavailableError(f"storage I/O failed: {type(exc).__name__}") from exc
        return removed

    async def put(self, key: str, data: bytes) -> PutResult:
        return await asyncio.to_thread(self._put_sync, key, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get_sync, key)

    async def head(self, key: str) -> BlobInfo | None:
        return await asyncio.to_thread(self._head_sync, key)

    async def delete(self, key: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, key)

    async def health(self) -> NodeHealth:
        return await asyncio.to_thread(self._health_sync)

    async def sweep_tmp(self, older_than_seconds: float) -> int:
        """Delete temporary files left by interrupted writes; returns how many were removed."""
        return await asyncio.to_thread(self._sweep_tmp_sync, older_than_seconds)
