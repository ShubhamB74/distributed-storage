import hashlib
import logging

import pytest

from tests.integration.api.conftest import ApiFactory
from tests.integration.api.helpers import SECRET, Api


async def test_register_then_duplicate_is_rejected(api: Api) -> None:
    first = await api.register()
    assert first.status_code == 201
    assert "user_id" in first.json()
    second = await api.register()
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "email_taken"


async def test_registration_can_be_disabled(api_factory: ApiFactory) -> None:
    async with api_factory(allow_registration=False) as api:
        response = await api.register()
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "registration_disabled"


async def test_a_weak_secret_is_rejected_without_echoing_it(api: Api) -> None:
    response = await api.register(secret="too-short")
    assert response.status_code == 422
    assert "too-short" not in response.text


async def test_login_returns_a_bearer_token_that_authenticates(api: Api) -> None:
    token = await api.user_token()
    response = await api.client.get("/v1/devices", headers=api.auth(token))
    assert response.status_code == 200


async def test_wrong_secret_and_unknown_account_are_indistinguishable(api: Api) -> None:
    await api.register()
    wrong = await api.login(secret="a-completely-different-secret-value")
    unknown = await api.login(email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    wrong_error, unknown_error = wrong.json()["error"], unknown.json()["error"]
    assert wrong_error["code"] == unknown_error["code"] == "invalid_credentials"
    assert wrong_error["message"] == unknown_error["message"]


async def test_account_locks_after_repeated_failures_even_for_the_right_secret(api: Api) -> None:
    await api.register()
    for _ in range(3):
        assert (await api.login(secret="wrong-secret-value-123456")).status_code == 401
    locked = await api.login()  # correct secret, but the account is locked
    assert locked.status_code == 401
    assert locked.json()["error"]["code"] == "invalid_credentials"
    rows = await api.sql("SELECT failed_login_count, locked_until FROM users")
    assert rows[0][0] == 3
    assert rows[0][1] is not None


async def test_a_successful_login_resets_the_failure_counter(api: Api) -> None:
    await api.register()
    for _ in range(2):
        await api.login(secret="wrong-secret-value-123456")
    assert (await api.login()).status_code == 200
    rows = await api.sql("SELECT failed_login_count, locked_until FROM users")
    assert rows[0] == (0, None)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-real-token"},
        {"Authorization": "Basic YWxpY2U6cGFzcw=="},
        {"Authorization": "Bearer " + "x" * 500},
    ],
)
async def test_missing_or_invalid_credentials_get_a_uniform_401(
    api: Api, headers: dict[str, str]
) -> None:
    response = await api.client.get("/v1/devices", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "unauthorized"


async def test_logout_revokes_the_token(api: Api) -> None:
    token = await api.user_token()
    assert (await api.client.post("/v1/auth/logout", headers=api.auth(token))).status_code == 204
    assert (await api.client.get("/v1/devices", headers=api.auth(token))).status_code == 401


async def test_expired_sessions_are_rejected(api: Api) -> None:
    token = await api.user_token()
    await api.sql(
        "UPDATE sessions SET created_at = now() - interval '2 hours', "
        "expires_at = now() - interval '1 hour'"
    )
    assert (await api.client.get("/v1/devices", headers=api.auth(token))).status_code == 401


async def test_disabled_accounts_cannot_log_in_or_use_existing_tokens(api: Api) -> None:
    token = await api.user_token()
    await api.sql("UPDATE users SET status = 'disabled'")
    assert (await api.client.get("/v1/devices", headers=api.auth(token))).status_code == 401
    assert (await api.login()).status_code == 401


async def test_only_a_hash_of_the_token_is_stored(api: Api) -> None:
    token = await api.user_token()
    rows = await api.sql("SELECT token_hash FROM sessions")
    assert len(rows) == 1
    assert bytes(rows[0][0]) == hashlib.sha256(token.encode()).digest()
    verifiers = await api.sql("SELECT auth_verifier FROM users")
    assert verifiers[0][0].startswith("$argon2id$")
    assert SECRET not in verifiers[0][0]


async def test_secrets_and_tokens_never_appear_in_logs(
    api: Api, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    token = await api.user_token()
    await api.login(secret="a-wrong-secret-that-must-not-be-logged")
    await api.client.get("/v1/devices", headers=api.auth(token))
    everything = "\n".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    for sensitive in (SECRET, token, "a-wrong-secret-that-must-not-be-logged"):
        assert sensitive not in everything
