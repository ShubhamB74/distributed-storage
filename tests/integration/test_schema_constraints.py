"""The Phase 1 schema enforces its invariants in the database itself."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from distributed_storage.core.config import Settings
from distributed_storage.db.engine import create_engine

AlembicRunner = Callable[..., Awaitable[tuple[int, str, str]]]

HASH = b"\x01" * 32


@pytest_asyncio.fixture
async def engine(migrated_database: Settings) -> AsyncIterator[AsyncEngine]:
    created = create_engine(migrated_database)
    try:
        yield created
    finally:
        await created.dispose()


async def _run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def _insert(engine: AsyncEngine, sql: str, **params: Any) -> uuid.UUID:
    async with engine.begin() as connection:
        value = (await connection.execute(text(sql + " RETURNING id"), params)).scalar_one()
    assert isinstance(value, uuid.UUID)
    return value


async def _user(engine: AsyncEngine, email: str = "user@example.com") -> uuid.UUID:
    return await _insert(
        engine,
        "INSERT INTO users (email, auth_scheme, auth_verifier) "
        "VALUES (:email, 'argon2id-secret-v1', 'verifier')",
        email=email,
    )


async def _device(engine: AsyncEngine, user_id: uuid.UUID, name: str = "laptop") -> uuid.UUID:
    return await _insert(
        engine,
        "INSERT INTO devices (user_id, name) VALUES (:user_id, :name)",
        user_id=user_id,
        name=name,
    )


async def _file(engine: AsyncEngine, owner_id: uuid.UUID) -> uuid.UUID:
    return await _insert(engine, "INSERT INTO files (owner_id) VALUES (:owner)", owner=owner_id)


async def _version(
    engine: AsyncEngine,
    file_id: uuid.UUID,
    number: int = 1,
    state: str = "planned",
    committed_at: datetime | None = None,
    envelope: bytes = b"{}",
) -> uuid.UUID:
    return await _insert(
        engine,
        "INSERT INTO file_versions (file_id, version_number, state, size_bytes, metadata_format, "
        "metadata_envelope, committed_at) "
        "VALUES (:file_id, :number, :state, 10, 'dev-plain-v0', :envelope, :committed_at)",
        file_id=file_id,
        number=number,
        state=state,
        envelope=envelope,
        committed_at=committed_at,
    )


async def _stripe(engine: AsyncEngine, version_id: uuid.UUID, index: int = 0) -> uuid.UUID:
    return await _insert(
        engine,
        "INSERT INTO stripes (file_version_id, stripe_index, codec_id, data_shards, parity_shards, "
        "data_length) VALUES (:version_id, :index, 'none', 1, 0, 10)",
        version_id=version_id,
        index=index,
    )


async def _node(engine: AsyncEngine, name: str = "node-1", state: str = "healthy") -> uuid.UUID:
    return await _insert(
        engine,
        "INSERT INTO storage_nodes (name, adapter_type, location_ref, failure_domain_id, state) "
        "VALUES (:name, 'local', '/data', 'domain-1', :state)",
        name=name,
        state=state,
    )


async def test_email_must_be_unique(engine: AsyncEngine) -> None:
    await _user(engine, "same@example.com")
    with pytest.raises(IntegrityError):
        await _user(engine, "same@example.com")


@pytest.mark.parametrize("email", ["Upper@Example.com", " padded@example.com ", ""])
async def test_email_must_be_normalised(engine: AsyncEngine, email: str) -> None:
    with pytest.raises(IntegrityError):
        await _user(engine, email)


async def test_user_status_is_restricted(engine: AsyncEngine) -> None:
    with pytest.raises(IntegrityError):
        await _run(
            engine,
            "INSERT INTO users (email, auth_scheme, auth_verifier, status) "
            "VALUES ('a@example.com', 's', 'v', 'deleted')",
        )


async def test_device_names_are_unique_per_user_only(engine: AsyncEngine) -> None:
    first = await _user(engine, "one@example.com")
    second = await _user(engine, "two@example.com")
    await _device(engine, first, "laptop")
    await _device(engine, second, "laptop")  # another user may reuse the name
    with pytest.raises(IntegrityError):
        await _device(engine, first, "laptop")


@pytest.mark.parametrize("column", ["ed25519_public_key", "x25519_public_key"])
async def test_device_public_keys_must_be_32_bytes_when_present(
    engine: AsyncEngine, column: str
) -> None:
    user_id = await _user(engine)
    await _run(
        engine,
        f"INSERT INTO devices (user_id, name, {column}) VALUES (:user_id, 'ok', :key)",  # noqa: S608
        user_id=user_id,
        key=b"\x02" * 32,
    )
    with pytest.raises(IntegrityError):
        await _run(
            engine,
            f"INSERT INTO devices (user_id, name, {column}) VALUES (:user_id, 'bad', :key)",  # noqa: S608
            user_id=user_id,
            key=b"\x02" * 31,
        )


async def test_session_token_hash_is_unique_and_exactly_32_bytes(engine: AsyncEngine) -> None:
    user_id = await _user(engine)
    device_id = await _device(engine, user_id)
    expires = datetime.now(UTC) + timedelta(hours=1)
    insert = (
        "INSERT INTO sessions (user_id, device_id, token_hash, expires_at) "
        "VALUES (:user_id, :device_id, :token_hash, :expires_at)"
    )
    params = {"user_id": user_id, "device_id": device_id, "expires_at": expires}
    await _run(engine, insert, token_hash=HASH, **params)
    with pytest.raises(IntegrityError):
        await _run(engine, insert, token_hash=HASH, **params)
    with pytest.raises(IntegrityError):
        await _run(engine, insert, token_hash=b"\x03" * 31, **params)


async def test_session_must_expire_after_creation(engine: AsyncEngine) -> None:
    user_id = await _user(engine)
    device_id = await _device(engine, user_id)
    with pytest.raises(IntegrityError):
        await _run(
            engine,
            "INSERT INTO sessions (user_id, device_id, token_hash, expires_at) "
            "VALUES (:user_id, :device_id, :token_hash, now() - interval '1 hour')",
            user_id=user_id,
            device_id=device_id,
            token_hash=HASH,
        )


async def test_foreign_keys_restrict_deletion(engine: AsyncEngine) -> None:
    user_id = await _user(engine)
    await _device(engine, user_id)
    with pytest.raises(IntegrityError):
        await _run(engine, "DELETE FROM users WHERE id = :id", id=user_id)


async def test_version_numbers_are_unique_per_file_and_positive(engine: AsyncEngine) -> None:
    file_id = await _file(engine, await _user(engine))
    await _version(engine, file_id, number=1)
    with pytest.raises(IntegrityError):
        await _version(engine, file_id, number=1)
    with pytest.raises(IntegrityError):
        await _version(engine, file_id, number=0)


async def test_committed_version_requires_a_commit_timestamp(engine: AsyncEngine) -> None:
    file_id = await _file(engine, await _user(engine))
    with pytest.raises(IntegrityError):
        await _version(engine, file_id, number=1, state="committed", committed_at=None)
    await _version(engine, file_id, number=2, state="committed", committed_at=datetime.now(UTC))


async def test_metadata_envelope_is_capped_at_64_kib(engine: AsyncEngine) -> None:
    file_id = await _file(engine, await _user(engine))
    await _version(engine, file_id, number=1, envelope=b"x" * 65536)
    with pytest.raises(IntegrityError):
        await _version(engine, file_id, number=2, envelope=b"x" * 65537)


async def test_current_version_foreign_key_is_deferred_until_commit(engine: AsyncEngine) -> None:
    owner_id = await _user(engine)
    file_id, version_id = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as connection:  # the file may reference a version inserted later
        await connection.execute(
            text("INSERT INTO files (id, owner_id, current_version_id) VALUES (:f, :o, :v)"),
            {"f": file_id, "o": owner_id, "v": version_id},
        )
        await connection.execute(
            text(
                "INSERT INTO file_versions (id, file_id, version_number, size_bytes, "
                "metadata_format, metadata_envelope) VALUES (:v, :f, 1, 10, 'dev-plain-v0', '{}')"
            ),
            {"v": version_id, "f": file_id},
        )
    with pytest.raises(IntegrityError):  # a dangling reference fails when the transaction commits
        await _run(
            engine,
            "INSERT INTO files (owner_id, current_version_id) VALUES (:o, :v)",
            o=owner_id,
            v=uuid.uuid4(),
        )


async def test_stripe_and_shard_indexes_are_unique(engine: AsyncEngine) -> None:
    file_id = await _file(engine, await _user(engine))
    version_id = await _version(engine, file_id)
    stripe_id = await _stripe(engine, version_id, index=0)
    with pytest.raises(IntegrityError):
        await _stripe(engine, version_id, index=0)
    node_id = await _node(engine)
    insert = (
        "INSERT INTO shard_placements (stripe_id, shard_index, node_id) "
        "VALUES (:stripe_id, 0, :node_id)"
    )
    await _run(engine, insert, stripe_id=stripe_id, node_id=node_id)
    with pytest.raises(IntegrityError):
        await _run(engine, insert, stripe_id=stripe_id, node_id=node_id)


async def test_stored_placement_requires_hash_and_length(engine: AsyncEngine) -> None:
    file_id = await _file(engine, await _user(engine))
    stripe_id = await _stripe(engine, await _version(engine, file_id))
    node_id = await _node(engine)
    base = {"stripe_id": stripe_id, "node_id": node_id}
    with pytest.raises(IntegrityError):
        await _run(
            engine,
            "INSERT INTO shard_placements (stripe_id, shard_index, node_id, state) "
            "VALUES (:stripe_id, 0, :node_id, 'stored')",
            **base,
        )
    with pytest.raises(IntegrityError):
        await _run(
            engine,
            "INSERT INTO shard_placements (stripe_id, shard_index, node_id, content_hash, length) "
            "VALUES (:stripe_id, 1, :node_id, :hash, 10)",
            hash=b"\x01" * 31,
            **base,
        )
    await _run(
        engine,
        "INSERT INTO shard_placements "
        "(stripe_id, shard_index, node_id, state, content_hash, length) "
        "VALUES (:stripe_id, 2, :node_id, 'stored', :hash, 10)",
        hash=HASH,
        **base,
    )


async def test_storage_node_state_and_name_are_constrained(engine: AsyncEngine) -> None:
    await _node(engine, "node-1")
    with pytest.raises(IntegrityError):
        await _node(engine, "node-1")
    with pytest.raises(IntegrityError):
        await _node(engine, "node-2", state="exploded")


async def test_audit_events_are_append_only(engine: AsyncEngine) -> None:
    await _run(
        engine,
        "INSERT INTO audit_events (action, resource_type, outcome) "
        "VALUES ('user.registered', 'user', 'success')",
    )
    for statement in (
        "UPDATE audit_events SET action = 'tampered'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ):
        with pytest.raises(DBAPIError) as exc:
            await _run(engine, statement)
        assert "append-only" in str(exc.value)
    with pytest.raises(IntegrityError):
        await _run(
            engine,
            "INSERT INTO audit_events (action, resource_type, outcome) VALUES ('x', 'y', 'maybe')",
        )


async def test_downgrade_removes_every_object_the_migration_created(
    temp_database: Settings, alembic: AlembicRunner
) -> None:
    code, _, err = await alembic(temp_database, "upgrade", "head")
    assert code == 0, err
    code, _, err = await alembic(temp_database, "downgrade", "base")
    assert code == 0, err

    engine = create_engine(temp_database)
    try:
        async with engine.connect() as connection:
            tables = {
                row[0]
                for row in await connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            }
            functions = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM pg_proc WHERE proname = 'audit_events_forbid_change'"
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    assert tables == {"alembic_version"}
    assert functions == 0
