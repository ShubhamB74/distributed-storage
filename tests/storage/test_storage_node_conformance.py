"""Conformance suite: the contract every StorageNode adapter must satisfy (ADR-0002, ADR-0014)."""

import asyncio
import hashlib
import uuid

import pytest

from distributed_storage.storage.base import PutResult, StorageNode
from distributed_storage.storage.errors import (
    BlobConflictError,
    BlobNotFoundError,
    InvalidBlobKeyError,
)


def _key() -> str:
    return str(uuid.uuid4())


async def test_put_then_get_round_trips_and_reports_length_and_hash(node: StorageNode) -> None:
    key, data = _key(), b"hello distributed storage"
    result = await node.put(key, data)
    assert result == PutResult(length=len(data), sha256=hashlib.sha256(data).digest(), created=True)
    assert await node.get(key) == data


async def test_empty_blob_round_trips(node: StorageNode) -> None:
    key = _key()
    result = await node.put(key, b"")
    assert result.length == 0
    assert await node.get(key) == b""


async def test_one_mebibyte_blob_round_trips(node: StorageNode) -> None:
    key, data = _key(), bytes(range(256)) * 4096
    await node.put(key, data)
    assert await node.get(key) == data


async def test_put_of_identical_bytes_is_an_idempotent_no_op(node: StorageNode) -> None:
    key, data = _key(), b"same bytes"
    first = await node.put(key, data)
    second = await node.put(key, data)
    assert first.created is True
    assert second.created is False
    assert second.sha256 == first.sha256
    assert second.length == first.length


async def test_put_of_different_bytes_conflicts_and_keeps_the_original(
    node: StorageNode,
) -> None:
    key = _key()
    await node.put(key, b"original")
    with pytest.raises(BlobConflictError):
        await node.put(key, b"different")
    assert await node.get(key) == b"original"


async def test_get_of_missing_blob_raises_not_found(node: StorageNode) -> None:
    with pytest.raises(BlobNotFoundError):
        await node.get(_key())


async def test_head_reports_length_or_none(node: StorageNode) -> None:
    key = _key()
    assert await node.head(key) is None
    await node.put(key, b"12345")
    info = await node.head(key)
    assert info is not None
    assert info.length == 5


async def test_delete_is_idempotent_and_allows_key_reuse(node: StorageNode) -> None:
    key = _key()
    assert await node.delete(key) is False
    await node.put(key, b"data")
    assert await node.delete(key) is True
    assert await node.delete(key) is False
    with pytest.raises(BlobNotFoundError):
        await node.get(key)
    assert await node.head(key) is None
    await node.put(key, b"new data")
    assert await node.get(key) == b"new data"


@pytest.mark.parametrize(
    "bad_key",
    [
        "",
        "../../etc/passwd",
        "..\\..\\windows",
        "not-a-uuid",
        str(uuid.uuid4()).upper(),
        str(uuid.uuid4()).replace("-", ""),
        str(uuid.uuid4()) + "\n",
        str(uuid.uuid4()) + "/..",
        "/" + str(uuid.uuid4()),
        "\x00" + str(uuid.uuid4()),
    ],
)
async def test_invalid_keys_are_rejected_by_every_operation(
    node: StorageNode, bad_key: str
) -> None:
    with pytest.raises(InvalidBlobKeyError):
        await node.put(bad_key, b"x")
    with pytest.raises(InvalidBlobKeyError):
        await node.get(bad_key)
    with pytest.raises(InvalidBlobKeyError):
        await node.head(bad_key)
    with pytest.raises(InvalidBlobKeyError):
        await node.delete(bad_key)


async def test_concurrent_identical_puts_all_succeed_and_exactly_one_creates(
    node: StorageNode,
) -> None:
    key, data = _key(), b"concurrent" * 1000
    results = await asyncio.gather(*(node.put(key, data) for _ in range(8)))
    assert sum(result.created for result in results) == 1
    assert await node.get(key) == data


async def test_concurrent_conflicting_puts_have_exactly_one_winner(node: StorageNode) -> None:
    key = _key()
    first, second = b"a" * 500, b"b" * 500
    outcomes = await asyncio.gather(
        node.put(key, first), node.put(key, second), return_exceptions=True
    )
    winners = [outcome for outcome in outcomes if isinstance(outcome, PutResult)]
    conflicts = [outcome for outcome in outcomes if isinstance(outcome, BlobConflictError)]
    assert len(winners) == 1
    assert len(conflicts) == 1
    assert await node.get(key) in {first, second}


async def test_health_reports_a_working_node(node: StorageNode) -> None:
    health = await node.health()
    assert health.healthy is True
