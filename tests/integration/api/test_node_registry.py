from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker

from distributed_storage.storage.health import HealthThresholds
from distributed_storage.storage.registry import ensure_local_node, record_probe
from tests.integration.api.conftest import ApiFactory
from tests.integration.api.helpers import Api, FlakyNode

THRESHOLDS = HealthThresholds(failures_to_suspect=2, failures_to_down=4, successes_to_recover=2)


async def test_startup_registers_the_configured_node_once(api: Api) -> None:
    rows = await api.sql("SELECT name, adapter_type, failure_domain_id, state FROM storage_nodes")
    assert rows == [("local-1", "local", "local-1", "healthy")]


async def test_registration_is_idempotent(api: Api) -> None:
    factory = async_sessionmaker(api.engine, expire_on_commit=False)
    for _ in range(3):
        async with factory() as session:
            node = await ensure_local_node(session, api.settings)
            await session.commit()
            assert node.name == "local-1"
    assert (await api.sql("SELECT count(*) FROM storage_nodes"))[0][0] == 1


async def test_probe_results_are_persisted_with_hysteresis(api: Api) -> None:
    factory = async_sessionmaker(api.engine, expire_on_commit=False)

    async def probe(success: bool) -> str:
        async with factory() as session:
            record = await record_probe(
                session, name="local-1", success=success, thresholds=THRESHOLDS
            )
            await session.commit()
        assert record is not None
        return record.state.value

    assert [await probe(False) for _ in range(4)] == ["healthy", "suspect", "suspect", "down"]
    assert await probe(True) == "down"
    assert await probe(True) == "healthy"
    row = await api.sql(
        "SELECT state, consecutive_failures, consecutive_successes FROM storage_nodes"
    )
    assert row[0] == ("healthy", 0, 2)


async def test_probing_an_unknown_node_is_a_no_op(api: Api) -> None:
    factory = async_sessionmaker(api.engine, expire_on_commit=False)
    async with factory() as session:
        assert (
            await record_probe(session, name="ghost", success=True, thresholds=THRESHOLDS) is None
        )


async def test_storage_operations_feed_passive_health_tracking(api: Api) -> None:
    flaky = FlakyNode(api.app.state.storage_node)
    api.app.state.storage_node = flaky
    token = await api.user_token()
    path = (await api.create_file(token, 4)).json()["upload_path"]

    flaky.fail_puts = 2
    assert (await api.put_content(token, path, b"abcd")).status_code == 503
    assert (await api.put_content(token, path, b"abcd")).status_code == 503
    assert (await api.sql("SELECT state FROM storage_nodes"))[0][0] == "suspect"

    assert (await api.put_content(token, path, b"abcd")).status_code == 200
    row = await api.sql("SELECT consecutive_failures, consecutive_successes FROM storage_nodes")
    assert row[0] == (0, 1)


async def test_uploads_are_refused_while_the_node_is_down_or_retired(api: Api) -> None:
    token = await api.user_token()
    for state in ("down", "retired"):
        await api.sql("UPDATE storage_nodes SET state = :state", state=state)
        response = await api.create_file(token, 4)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "storage_unavailable"
    assert (await api.sql("SELECT count(*) FROM files"))[0][0] == 0
    await api.sql("UPDATE storage_nodes SET state = 'suspect'")
    assert (await api.create_file(token, 4)).status_code == 201  # suspect nodes still accept writes


async def test_readiness_includes_a_passing_storage_check(api: Api) -> None:
    response = await api.client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "migrations": "ok", "storage": "ok"}


async def test_readiness_fails_when_the_blob_root_is_unusable(
    api_factory: ApiFactory, tmp_path: Path
) -> None:
    blocker = tmp_path / "a-file-not-a-directory"
    blocker.write_bytes(b"x")
    async with api_factory(blob_root=blocker / "blobs") as api:
        response = await api.client.get("/readyz")
        liveness = await api.client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "migrations": "ok", "storage": "fail"}
    assert liveness.status_code == 200
