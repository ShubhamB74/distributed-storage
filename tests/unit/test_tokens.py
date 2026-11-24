import hashlib

from distributed_storage.auth.tokens import MAX_TOKEN_LENGTH, generate_token, hash_token


def test_tokens_are_unique_urlsafe_and_within_the_length_limit() -> None:
    tokens = {generate_token() for _ in range(200)}
    assert len(tokens) == 200
    for token in tokens:
        assert len(token) <= MAX_TOKEN_LENGTH
        assert all(char.isalnum() or char in "-_" for char in token)


def test_tokens_carry_at_least_256_bits() -> None:
    assert len(generate_token()) >= 43


def test_hash_is_sha256_of_the_token_and_not_the_token() -> None:
    token = generate_token()
    digest = hash_token(token)
    assert digest == hashlib.sha256(token.encode()).digest()
    assert len(digest) == 32
    assert token.encode() not in digest
