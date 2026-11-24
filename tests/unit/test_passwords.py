import pytest

from distributed_storage.auth.passwords import AUTH_SCHEME, PasswordVerifier


@pytest.fixture
def verifier() -> PasswordVerifier:
    # Minimal Argon2 cost: fast tests; production defaults live in Settings.
    return PasswordVerifier(time_cost=1, memory_cost_kib=8, parallelism=1)


async def test_hash_is_argon2id_and_never_contains_the_secret(verifier: PasswordVerifier) -> None:
    secret = "correct horse battery staple 123"
    encoded = await verifier.hash(secret)
    assert encoded.startswith("$argon2id$")
    assert secret not in encoded


async def test_verify_accepts_the_right_secret_and_rejects_others(
    verifier: PasswordVerifier,
) -> None:
    encoded = await verifier.hash("the right secret value")
    assert await verifier.verify(encoded, "the right secret value") is True
    assert await verifier.verify(encoded, "the wrong secret value") is False


async def test_verify_treats_a_malformed_verifier_as_a_failure(verifier: PasswordVerifier) -> None:
    assert await verifier.verify("not-a-valid-hash", "anything at all here") is False
    assert await verifier.verify("", "anything at all here") is False


async def test_hashes_are_salted(verifier: PasswordVerifier) -> None:
    assert await verifier.hash("same secret value 1234") != await verifier.hash(
        "same secret value 1234"
    )


async def test_dummy_verification_completes_without_raising(verifier: PasswordVerifier) -> None:
    await verifier.verify_dummy("whatever the caller sent")


async def test_needs_rehash_detects_weaker_parameters(verifier: PasswordVerifier) -> None:
    weak = await verifier.hash("some secret value 12345")
    assert verifier.needs_rehash(weak) is False
    stronger = PasswordVerifier(time_cost=2, memory_cost_kib=16, parallelism=1)
    assert stronger.needs_rehash(weak) is True
    assert stronger.needs_rehash("garbage") is True


def test_scheme_identifier_matches_the_data_model() -> None:
    assert AUTH_SCHEME == "argon2id-secret-v1"
