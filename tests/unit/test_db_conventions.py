from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from distributed_storage.db.base import NAMING_CONVENTION, Base
from distributed_storage.db.migrations import get_expected_head

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_base_uses_the_naming_convention() -> None:
    assert dict(Base.metadata.naming_convention) == NAMING_CONVENTION


def test_constraint_and_index_names_are_deterministic() -> None:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    table = Table(
        "widget",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("code", Integer, unique=True),
        Column("owner", Integer, index=True),
    )

    ddl = str(
        CreateTable(table).compile(
            dialect=postgresql.dialect()  # type: ignore[no-untyped-call]
        )
    )
    assert "CONSTRAINT pk_widget PRIMARY KEY" in ddl
    assert "CONSTRAINT uq_widget_code UNIQUE" in ddl

    index_ddl = str(
        CreateIndex(next(iter(table.indexes))).compile(
            dialect=postgresql.dialect()  # type: ignore[no-untyped-call]
        )
    )
    assert "ix_widget_owner" in index_ddl


def test_migration_history_has_a_single_head() -> None:
    assert get_expected_head(REPO_ROOT / "alembic.ini") == "0001"
