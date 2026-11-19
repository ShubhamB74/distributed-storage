"""Helpers for reasoning about Alembic migration state."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def get_expected_head(config_path: Path) -> str:
    """Return the single migration head the code expects the database to be at."""
    script = ScriptDirectory.from_config(Config(str(config_path)))
    head = script.get_current_head()  # raises if there are multiple heads
    if head is None:
        raise RuntimeError("no migration revisions found")
    return head
