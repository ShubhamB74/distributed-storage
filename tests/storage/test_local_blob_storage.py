"""Behaviour specific to LocalBlobStorage (layout, limits, health, sweeping)."""

import asyncio
import os
import time
import uuid
from pathlib import Path

import pytest

from distributed_storage.storage.errors import BlobTooLargeError, InvalidBlobKeyError
from distributed_storage.storage.local import LocalBlobStorage


async def test_blob_is_stored_under_a_sharded_path_and_temp_dir_is_clean(tmp_path: Path) -> None:
    root = tmp_path / "node"
    node = LocalBlobStorage(root)
    key = str(uuid.uuid4())
    await node.put(key, b"payload")
    assert (root / "blobs" / key[:2] / key).read_bytes() == b"payload"
    assert list(node.tmp_dir.iterdir()) == []


async def test_rejected_keys_touch_nothing_on_disk(tmp_path: Path) -> None:
    root = tmp_path / "node"
    node = LocalBlobStorage(root)
    with pytest.raises(InvalidBlobKeyError):
        await node.put("../../escape", b"x")
    assert not root.exists()
    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == []


async def test_a_second_instance_on_the_same_root_sees_existing_blobs(tmp_path: Path) -> None:
    key = str(uuid.uuid4())
    await LocalBlobStorage(tmp_path / "node").put(key, b"persisted")
    assert await LocalBlobStorage(tmp_path / "node").get(key) == b"persisted"


async def test_size_limit_applies_to_put_and_get(tmp_path: Path) -> None:
    root = tmp_path / "node"
    small = LocalBlobStorage(root, max_blob_bytes=10)
    with pytest.raises(BlobTooLargeError):
        await small.put(str(uuid.uuid4()), b"x" * 11)
    key = str(uuid.uuid4())
    await LocalBlobStorage(root).put(key, b"x" * 11)
    with pytest.raises(BlobTooLargeError):
        await small.get(key)


async def test_sweep_removes_only_stale_temp_files(tmp_path: Path) -> None:
    node = LocalBlobStorage(tmp_path / "node")
    node.tmp_dir.mkdir(parents=True)
    stale = node.tmp_dir / "stale.tmp"
    fresh = node.tmp_dir / "fresh.tmp"
    stale.write_bytes(b"x")
    fresh.write_bytes(b"y")
    old = time.time() - 7200
    os.utime(stale, (old, old))
    assert await node.sweep_tmp(3600) == 1
    assert not stale.exists()
    assert fresh.exists()


async def test_sweep_on_a_node_that_never_wrote_returns_zero(tmp_path: Path) -> None:
    assert await LocalBlobStorage(tmp_path / "node").sweep_tmp(0) == 0


async def test_health_reports_free_space(tmp_path: Path) -> None:
    health = await LocalBlobStorage(tmp_path / "node").health()
    assert health.healthy is True
    assert health.free_bytes is not None
    assert health.free_bytes > 0


async def test_health_fails_when_the_root_is_not_a_directory(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_bytes(b"i am a file")
    health = await LocalBlobStorage(blocker).health()
    assert health.healthy is False
    assert str(blocker) not in health.detail
