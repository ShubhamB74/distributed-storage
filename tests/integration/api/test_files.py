import base64
import hashlib
import json
import uuid

from tests.integration.api.conftest import ApiFactory
from tests.integration.api.helpers import Api, FlakyNode, envelope


async def test_file_endpoints_are_hidden_unless_the_dev_flag_is_on(api_factory: ApiFactory) -> None:
    async with api_factory(allow_dev_plaintext_upload=False) as api:
        token = await api.user_token()
        response = await api.create_file(token, 10)
    assert response.status_code == 404


async def test_upload_then_download_is_byte_identical_and_verified(api: Api) -> None:
    token = await api.user_token()
    data = bytes(range(256)) * 40
    file_id, version_id = await api.upload(token, data)

    response = await api.client.get(
        f"/v1/files/{file_id}/versions/{version_id}/content", headers=api.auth(token)
    )
    assert response.status_code == 200
    assert response.content == data
    assert response.headers["x-content-sha256"] == hashlib.sha256(data).hexdigest()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-development-only"] == "plaintext-storage"

    version = await api.sql("SELECT state, committed_at FROM file_versions")
    assert version[0][0] == "committed"
    assert version[0][1] is not None
    placement = await api.sql("SELECT state, content_hash, length FROM shard_placements")
    assert placement[0][0] == "stored"
    assert bytes(placement[0][1]) == hashlib.sha256(data).digest()
    assert placement[0][2] == len(data)
    current = await api.sql("SELECT current_version_id FROM files")
    assert str(current[0][0]) == version_id


async def test_metadata_round_trips_as_an_opaque_envelope(api: Api) -> None:
    token = await api.user_token()
    file_id, _ = await api.upload(token, b"hello", name="report.pdf")
    body = (await api.client.get(f"/v1/files/{file_id}", headers=api.auth(token))).json()
    assert len(body["versions"]) == 1
    version = body["versions"][0]
    assert version["state"] == "committed"
    assert json.loads(base64.b64decode(version["metadata_envelope"])) == {"name": "report.pdf"}


async def test_repeating_the_same_upload_is_idempotent_but_different_bytes_conflict(
    api: Api,
) -> None:
    token = await api.user_token()
    created = (await api.create_file(token, 6)).json()
    path = created["upload_path"]
    first = await api.put_content(token, path, b"abcdef")
    again = await api.put_content(token, path, b"abcdef")
    different = await api.put_content(token, path, b"ABCDEF")
    assert first.status_code == 200
    assert first.json()["idempotent"] is False
    assert again.status_code == 200
    assert again.json()["idempotent"] is True
    assert different.status_code == 409
    assert different.json()["error"]["code"] == "content_conflict"
    download = await api.client.get(path, headers=api.auth(token))
    assert download.content == b"abcdef"


async def test_size_limits_and_mismatches(api: Api) -> None:
    token = await api.user_token()
    too_big = await api.create_file(token, api.settings.max_upload_bytes + 1)
    assert too_big.status_code == 413

    path = (await api.create_file(token, 10)).json()["upload_path"]
    assert (await api.put_content(token, path, b"x" * 11)).status_code == 413
    assert (await api.put_content(token, path, b"x" * 9)).status_code == 400
    assert (await api.put_content(token, path, b"x" * 10)).status_code == 200


async def test_the_metadata_envelope_is_capped(api: Api) -> None:
    token = await api.user_token()
    response = await api.client.post(
        "/v1/files",
        headers=api.auth(token),
        json={
            "metadata_format": "dev-plain-v0",
            "metadata_envelope": base64.b64encode(b"x" * 65537).decode(),
            "size_bytes": 5,
        },
    )
    assert response.status_code == 422
    assert (await api.create_file(token, 5)).status_code == 201


async def test_files_are_invisible_to_other_users_and_attempts_are_audited(api: Api) -> None:
    alice = await api.user_token("alice")
    bob = await api.user_token("bob")
    file_id, version_id = await api.upload(alice, b"alice's secret notes")
    content_path = f"/v1/files/{file_id}/versions/{version_id}/content"

    assert (await api.client.get(f"/v1/files/{file_id}", headers=api.auth(bob))).status_code == 404
    assert (await api.client.get(content_path, headers=api.auth(bob))).status_code == 404
    assert (await api.put_content(bob, content_path, b"overwrite!")).status_code == 404
    unknown = await api.client.get(f"/v1/files/{uuid.uuid4()}", headers=api.auth(bob))
    assert unknown.status_code == 404

    bob_list = (await api.client.get("/v1/files", headers=api.auth(bob))).json()
    assert bob_list["items"] == []
    assert len(await api.audit("authz.denied")) == 3  # the unknown id is not an authz event
    stored = await api.client.get(content_path, headers=api.auth(alice))
    assert stored.content == b"alice's secret notes"


async def test_file_endpoints_require_authentication(api: Api) -> None:
    assert (await api.client.get("/v1/files")).status_code == 401
    assert (await api.client.post("/v1/files", json={})).status_code == 401


async def test_listing_is_paginated_with_a_cursor(api: Api) -> None:
    token = await api.user_token()
    ids = [(await api.upload(token, b"data", name=f"f{i}"))[0] for i in range(3)]

    first = (await api.client.get("/v1/files?limit=2", headers=api.auth(token))).json()
    assert [item["id"] for item in first["items"]] == ids[:2]
    assert first["next_after"] == ids[1]
    assert first["items"][0]["current_version"]["state"] == "committed"

    cursor = first["next_after"]
    second = (
        await api.client.get(f"/v1/files?limit=2&after={cursor}", headers=api.auth(token))
    ).json()
    assert [item["id"] for item in second["items"]] == ids[2:]
    assert second["next_after"] is None

    bad = await api.client.get(f"/v1/files?after={uuid.uuid4()}", headers=api.auth(token))
    assert bad.status_code == 400
    assert (await api.client.get("/v1/files?limit=0", headers=api.auth(token))).status_code == 422


async def test_downloading_a_version_without_content_is_a_conflict(api: Api) -> None:
    token = await api.user_token()
    created = (await api.create_file(token, 10)).json()
    response = await api.client.get(created["upload_path"], headers=api.auth(token))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_committed"


async def test_a_storage_outage_during_upload_leaves_the_version_planned_and_retry_succeeds(
    api: Api,
) -> None:
    flaky = FlakyNode(api.app.state.storage_node)
    api.app.state.storage_node = flaky
    token = await api.user_token()
    created = (await api.create_file(token, 8)).json()

    flaky.fail_puts = 1
    failed = await api.put_content(token, created["upload_path"], b"12345678")
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "storage_unavailable"
    state = await api.sql("SELECT state FROM file_versions")
    assert state[0][0] == "planned"
    placement = await api.sql("SELECT state, content_hash FROM shard_placements")
    assert placement[0] == ("planned", None)
    node = await api.sql("SELECT consecutive_failures FROM storage_nodes")
    assert node[0][0] == 1

    retried = await api.put_content(token, created["upload_path"], b"12345678")
    assert retried.status_code == 200
    assert (await api.client.get(created["upload_path"], headers=api.auth(token))).content == (
        b"12345678"
    )


async def test_a_corrupted_blob_is_detected_and_nothing_is_returned(api: Api) -> None:
    token = await api.user_token()
    data = b"precious data " * 100
    file_id, version_id = await api.upload(token, data)
    shard_id = str((await api.sql("SELECT id FROM shard_placements"))[0][0])
    blob = api.settings.blob_root / "blobs" / shard_id[:2] / shard_id
    blob.write_bytes(b"x" * len(data))  # same length, different bytes

    response = await api.client.get(
        f"/v1/files/{file_id}/versions/{version_id}/content", headers=api.auth(token)
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "integrity_error"
    assert b"xxxx" not in response.content
    events = await api.audit("integrity.mismatch")
    assert len(events) == 1
    assert events[0][4]["reason"] == "hash_mismatch"


async def test_a_missing_blob_is_reported_as_an_integrity_failure(api: Api) -> None:
    token = await api.user_token()
    file_id, version_id = await api.upload(token, b"will be lost")
    shard_id = str((await api.sql("SELECT id FROM shard_placements"))[0][0])
    assert await api.app.state.storage_node.delete(shard_id) is True

    response = await api.client.get(
        f"/v1/files/{file_id}/versions/{version_id}/content", headers=api.auth(token)
    )
    assert response.status_code == 500
    events = await api.audit("integrity.mismatch")
    assert events[0][4]["reason"] == "blob_missing"


async def test_envelope_helper_matches_what_the_api_decodes() -> None:
    assert json.loads(base64.b64decode(envelope("a.txt"))) == {"name": "a.txt"}
