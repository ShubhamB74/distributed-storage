from collections.abc import AsyncIterator

import pytest

from distributed_storage.api.errors import ApiError
from distributed_storage.files.body import read_limited


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def test_exact_body_is_returned_whole_across_chunks() -> None:
    assert await read_limited(_chunks(b"ab", b"cd", b"e"), expected=5) == b"abcde"


async def test_oversize_body_is_rejected_with_413_before_reading_the_rest() -> None:
    consumed: list[int] = []

    async def stream() -> AsyncIterator[bytes]:
        for index in range(100):
            consumed.append(index)
            yield b"xxxx"

    with pytest.raises(ApiError) as exc:
        await read_limited(stream(), expected=10)
    assert exc.value.status_code == 413
    assert len(consumed) < 10


async def test_short_body_is_rejected_with_400() -> None:
    with pytest.raises(ApiError) as exc:
        await read_limited(_chunks(b"abc"), expected=10)
    assert exc.value.status_code == 400
    assert exc.value.code == "size_mismatch"


async def test_empty_body_is_short_unless_zero_was_expected() -> None:
    with pytest.raises(ApiError):
        await read_limited(_chunks(), expected=1)
    assert await read_limited(_chunks(), expected=0) == b""
