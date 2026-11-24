"""Opaque bearer session tokens (D16): 256 random bits, stored only as a SHA-256 hash."""

import hashlib
import secrets

TOKEN_BYTES = 32
MAX_TOKEN_LENGTH = 128


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> bytes:
    # The token carries 256 bits of entropy, so an unsalted fast hash is sufficient: there is
    # nothing to brute-force and a database leak does not reveal usable tokens.
    return hashlib.sha256(token.encode("utf-8")).digest()
