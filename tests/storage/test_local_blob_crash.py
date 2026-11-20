"""Crash and I/O-failure injection for LocalBlobStorage's write path."""

import errno
import uuid
from pathlib import Path

import pytest

from distributed_storage.storage.errors import BlobNotFoundError, StorageUnavailableError
from distributed_storage.storage.local import LocalBlobStorage


async def test_crash_after_temp_write_leaves_no_visible_blob_and_retry_succeeds(
    tmp_path: Path,
) -> None:
    node = LocalBlobStorage(tmp_path / "node")
    key, data = str(uuid.uuid4()), b"will survive a retry"

    # Simulate the process dying after the temp file is written but before publishing.
    node.tmp_dir.mkdir(parents=True)
    node._write_temp(node.tmp_dir / f"{key}.crashed.tmp", data)

    assert await node.head(key) is None
    with pytest.raises(BlobNotFoundError):
        await node.get(key)

    result = await node.put(key, data)
    assert result.created is True
    assert await node.get(key) == data

    assert await node.sweep_tmp(0) == 1  # the crashed temp file is cleaned up
    assert list(node.tmp_dir.iterdir()) == []


async def test_publish_failure_is_reported_cleans_up_and_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = LocalBlobStorage(tmp_path / "node")
    key, data = str(uuid.uuid4()), b"payload"

    def failing_publish(self: LocalBlobStorage, tmp: Path, final: Path) -> None:
        raise OSError(errno.EIO, "simulated I/O error")

    with monkeypatch.context() as patch:
        patch.setattr(LocalBlobStorage, "_publish", failing_publish)
        with pytest.raises(StorageUnavailableError):
            await node.put(key, data)

    assert await node.head(key) is None
    assert list(node.tmp_dir.iterdir()) == []
    assert (await node.put(key, data)).created is True
    assert await node.get(key) == data


async def test_disk_full_while_writing_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = LocalBlobStorage(tmp_path / "node")
    key = str(uuid.uuid4())

    def partial_write_then_enospc(self: LocalBlobStorage, tmp: Path, data: bytes) -> None:
        tmp.write_bytes(data[: len(data) // 2])
        raise OSError(errno.ENOSPC, "simulated disk full")

    with monkeypatch.context() as patch:
        patch.setattr(LocalBlobStorage, "_write_temp", partial_write_then_enospc)
        with pytest.raises(StorageUnavailableError):
            await node.put(key, b"x" * 1000)

    assert await node.head(key) is None
    assert list(node.tmp_dir.iterdir()) == []


async def test_unexpected_errors_propagate_but_still_clean_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = LocalBlobStorage(tmp_path / "node")
    key = str(uuid.uuid4())

    def buggy_publish(self: LocalBlobStorage, tmp: Path, final: Path) -> None:
        raise RuntimeError("programmer error")

    with monkeypatch.context() as patch:
        patch.setattr(LocalBlobStorage, "_publish", buggy_publish)
        with pytest.raises(RuntimeError):
            await node.put(key, b"data")

    assert await node.head(key) is None
    assert list(node.tmp_dir.iterdir()) == []
