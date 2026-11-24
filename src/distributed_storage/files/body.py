"""Bounded request-body reading."""

from collections.abc import AsyncIterator

from distributed_storage.api.errors import ApiError


async def read_limited(stream: AsyncIterator[bytes], *, expected: int) -> bytes:
    """Read exactly ``expected`` bytes, stopping as soon as the body exceeds it.

    Raises 413 for an oversize body (without buffering the rest) and 400 for a short one.
    """
    buffer = bytearray()
    async for chunk in stream:
        buffer.extend(chunk)
        if len(buffer) > expected:
            raise ApiError(413, "payload_too_large", "the body is larger than the declared size")
    if len(buffer) != expected:
        raise ApiError(400, "size_mismatch", "the body is smaller than the declared size")
    return bytes(buffer)
