import json
from collections import Counter

from tests.integration.api.helpers import SECRET, Api


async def test_each_security_relevant_action_produces_exactly_one_event(api: Api) -> None:
    alice_token = await api.user_token("alice")  # register + login
    bob_token = await api.user_token("bob")
    await api.login(email="alice@example.com", secret="a-wrong-secret-value-123456")

    file_id, version_id = await api.upload(alice_token, b"audited bytes")  # created + stored
    content = f"/v1/files/{file_id}/versions/{version_id}/content"
    await api.client.get(content, headers=api.auth(alice_token))  # downloaded
    await api.client.get(content, headers=api.auth(bob_token))  # denied

    shard_id = str((await api.sql("SELECT id FROM shard_placements"))[0][0])
    blob = api.settings.blob_root / "blobs" / shard_id[:2] / shard_id
    blob.write_bytes(b"y" * 13)
    await api.client.get(content, headers=api.auth(alice_token))  # integrity mismatch

    devices = (await api.client.get("/v1/devices", headers=api.auth(alice_token))).json()
    other_device = devices[0]["id"]
    await api.client.delete(f"/v1/devices/{other_device}", headers=api.auth(bob_token))  # denied
    await api.client.post("/v1/auth/logout", headers=api.auth(bob_token))  # logout

    events = await api.audit()
    counts = Counter((event[0], event[1]) for event in events)
    assert counts == Counter(
        {
            ("user.registered", "success"): 2,
            ("auth.login", "success"): 2,
            ("auth.login", "failure"): 1,
            ("file.created", "success"): 1,
            ("file.content_stored", "success"): 1,
            ("file.downloaded", "success"): 1,
            ("authz.denied", "denied"): 2,
            ("integrity.mismatch", "failure"): 1,
            ("auth.logout", "success"): 1,
        }
    )


async def test_events_carry_request_ids_and_contain_no_secrets_or_emails(api: Api) -> None:
    token = await api.user_token()
    await api.login(secret="another-wrong-secret-value-1")
    await api.upload(token, b"data")

    events = await api.audit()
    assert events
    for event in events:
        assert event[5], f"{event[0]} has no request id"
    serialised = json.dumps([event[4] for event in events])
    assert "@" not in serialised
    assert SECRET not in serialised
    assert token not in serialised


async def test_failed_logins_record_a_reason_but_not_the_attempted_secret(api: Api) -> None:
    await api.register()
    await api.login(secret="another-wrong-secret-value-1")
    await api.login(email="ghost@example.com")
    reasons = [event[4]["reason"] for event in await api.audit("auth.login")]
    assert reasons == ["wrong_secret", "unknown_account"]
