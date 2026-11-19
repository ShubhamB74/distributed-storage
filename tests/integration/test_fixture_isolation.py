"""Meta-tests: the database fixtures really isolate tests from each other and from dev data."""

from collections.abc import Awaitable, Callable

from sqlalchemy import text

from distributed_storage.core.config import Settings
from distributed_storage.db.engine import create_engine

DatabaseFactory = Callable[[], Awaitable[Settings]]


async def test_each_database_is_unique_and_not_the_configured_one(
    database_factory: DatabaseFactory, base_settings: Settings
) -> None:
    first = await database_factory()
    second = await database_factory()
    assert first.db_name != second.db_name
    assert base_settings.db_name not in {first.db_name, second.db_name}
    assert first.db_name.startswith("distributed_storage_test_")


async def test_changes_in_one_database_are_invisible_in_another(
    database_factory: DatabaseFactory,
) -> None:
    first = await database_factory()
    second = await database_factory()

    first_engine = create_engine(first)
    second_engine = create_engine(second)
    try:
        async with first_engine.begin() as connection:
            await connection.execute(text("CREATE TABLE isolation_probe (id integer)"))
        async with second_engine.connect() as connection:
            exists = await connection.execute(text("SELECT to_regclass('isolation_probe')"))
            assert exists.scalar_one() is None
    finally:
        await first_engine.dispose()
        await second_engine.dispose()
