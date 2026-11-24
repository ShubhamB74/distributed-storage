import uuid

from tests.integration.api.helpers import Api


async def test_login_creates_a_device_and_a_repeat_login_reuses_it(api: Api) -> None:
    await api.user_token(device="laptop")
    second = await api.login(device="laptop")
    assert second.status_code == 200
    token = second.json()["access_token"]
    devices = (await api.client.get("/v1/devices", headers=api.auth(token))).json()
    assert len(devices) == 1
    assert devices[0]["name"] == "laptop"
    assert devices[0]["id"] == second.json()["device_id"]
    assert devices[0]["is_current"] is True


async def test_each_device_name_is_a_separate_device(api: Api) -> None:
    laptop = await api.user_token(device="laptop")
    await api.user_token(device="phone")
    devices = (await api.client.get("/v1/devices", headers=api.auth(laptop))).json()
    assert {d["name"] for d in devices} == {"laptop", "phone"}
    assert [d["name"] for d in devices if d["is_current"]] == ["laptop"]


async def test_users_only_see_their_own_devices(api: Api) -> None:
    alice = await api.user_token("alice")
    bob = await api.user_token("bob")
    alice_devices = (await api.client.get("/v1/devices", headers=api.auth(alice))).json()
    bob_devices = (await api.client.get("/v1/devices", headers=api.auth(bob))).json()
    assert len(alice_devices) == len(bob_devices) == 1
    assert alice_devices[0]["id"] != bob_devices[0]["id"]


async def test_another_users_device_cannot_be_revoked_and_the_attempt_is_audited(api: Api) -> None:
    alice = await api.user_token("alice")
    bob = await api.user_token("bob")
    alice_device = (await api.client.get("/v1/devices", headers=api.auth(alice))).json()[0]["id"]

    response = await api.client.delete(f"/v1/devices/{alice_device}", headers=api.auth(bob))
    assert response.status_code == 404
    assert (await api.client.get("/v1/devices", headers=api.auth(alice))).status_code == 200

    denied = await api.audit("authz.denied")
    assert len(denied) == 1
    assert denied[0][1] == "denied"
    assert denied[0][3] == alice_device


async def test_unknown_device_ids_return_404(api: Api) -> None:
    token = await api.user_token()
    response = await api.client.delete(f"/v1/devices/{uuid.uuid4()}", headers=api.auth(token))
    assert response.status_code == 404


async def test_revoking_a_device_kills_its_sessions_but_not_the_others(api: Api) -> None:
    laptop = await api.user_token(device="laptop")
    phone = await api.user_token(device="phone")
    devices = (await api.client.get("/v1/devices", headers=api.auth(laptop))).json()
    phone_id = next(d["id"] for d in devices if d["name"] == "phone")

    response = await api.client.delete(f"/v1/devices/{phone_id}", headers=api.auth(laptop))
    assert response.status_code == 204
    assert (await api.client.get("/v1/devices", headers=api.auth(phone))).status_code == 401
    assert (await api.client.get("/v1/devices", headers=api.auth(laptop))).status_code == 200


async def test_a_device_can_revoke_itself(api: Api) -> None:
    token = await api.user_token()
    own = (await api.client.get("/v1/devices", headers=api.auth(token))).json()[0]["id"]
    assert (
        await api.client.delete(f"/v1/devices/{own}", headers=api.auth(token))
    ).status_code == 204
    assert (await api.client.get("/v1/devices", headers=api.auth(token))).status_code == 401


async def test_revocation_is_idempotent_and_audited_once(api: Api) -> None:
    laptop = await api.user_token(device="laptop")
    await api.user_token(device="phone")
    devices = (await api.client.get("/v1/devices", headers=api.auth(laptop))).json()
    phone_id = next(d["id"] for d in devices if d["name"] == "phone")
    for _ in range(2):
        response = await api.client.delete(f"/v1/devices/{phone_id}", headers=api.auth(laptop))
        assert response.status_code == 204
    assert len(await api.audit("device.revoked")) == 1


async def test_a_revoked_device_name_cannot_log_in_again(api: Api) -> None:
    laptop = await api.user_token(device="laptop")
    await api.user_token(device="phone")
    devices = (await api.client.get("/v1/devices", headers=api.auth(laptop))).json()
    phone_id = next(d["id"] for d in devices if d["name"] == "phone")
    await api.client.delete(f"/v1/devices/{phone_id}", headers=api.auth(laptop))

    response = await api.login(device="phone")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "device_revoked"
    assert (await api.login(device="tablet")).status_code == 200
