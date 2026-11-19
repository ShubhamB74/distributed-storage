from collections.abc import Awaitable, Callable
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from distributed_storage.core.config import Settings
from distributed_storage.db.base import Base
from distributed_storage.db.engine import create_engine
from distributed_storage.db.migrations import get_expected_head

REPO_ROOT = Path(__file__).resolve().parents[2]

AlembicRunner = Callable[..., Awaitable[tuple[int, str, str]]]


async def _scalar(settings: Settings, statement: str) -> object:
    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            return (await connection.execute(text(statement))).scalar_one_or_none()
    finally:
        await engine.dispose()


async def test_migration_cycle_upgrade_downgrade_upgrade(
    temp_database: Settings, alembic: AlembicRunner
) -> None:
    for args in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
        code, _, err = await alembic(temp_database, *args)
        assert code == 0, f"alembic {' '.join(args)} failed: {err}"

    version = await _scalar(temp_database, "SELECT version_num FROM alembic_version")
    assert version == get_expected_head(REPO_ROOT / "alembic.ini")


async def test_downgrade_to_base_leaves_no_recorded_revision(
    migrated_database: Settings, alembic: AlembicRunner
) -> None:
    code, _, err = await alembic(migrated_database, "downgrade", "base")
    assert code == 0, err
    assert await _scalar(migrated_database, "SELECT version_num FROM alembic_version") is None


async def test_baseline_creates_no_application_tables(migrated_database: Settings) -> None:
    engine = create_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
            tables = {row[0] for row in result}
    finally:
        await engine.dispose()
    assert tables == {"alembic_version"}


async def test_models_and_migrations_have_no_drift(migrated_database: Settings) -> None:
    engine = create_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(
                lambda sync_conn: compare_metadata(
                    MigrationContext.configure(sync_conn), Base.metadata
                )
            )
    finally:
        await engine.dispose()
    assert differences == []
