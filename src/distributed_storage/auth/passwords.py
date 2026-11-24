"""Argon2id verifier for the client-supplied ``auth_secret`` (ADR-0011).

The server never sees a password-derived key-derivation secret: the verifier is computed from
the separate authentication secret only. Hashing is CPU and memory heavy, so it runs in a
worker thread.
"""

import asyncio

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

AUTH_SCHEME = "argon2id-secret-v1"
_DUMMY_SECRET = "dummy-secret-used-only-to-equalise-timing"  # noqa: S105


class PasswordVerifier:
    def __init__(self, *, time_cost: int, memory_cost_kib: int, parallelism: int) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost_kib,
            parallelism=parallelism,
            type=Type.ID,
        )
        # Verified against when the account does not exist (or may not log in), so the response
        # time does not reveal which case occurred.
        self._dummy_verifier = self._hasher.hash(_DUMMY_SECRET)

    def _verify(self, verifier: str, secret: str) -> bool:
        try:
            return self._hasher.verify(verifier, secret)
        except (VerifyMismatchError, InvalidHashError, VerificationError):
            return False

    async def hash(self, secret: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, secret)

    async def verify(self, verifier: str, secret: str) -> bool:
        return await asyncio.to_thread(self._verify, verifier, secret)

    async def verify_dummy(self, secret: str) -> None:
        await asyncio.to_thread(self._verify, self._dummy_verifier, secret)

    def needs_rehash(self, verifier: str) -> bool:
        try:
            return self._hasher.check_needs_rehash(verifier)
        except InvalidHashError:
            return True
