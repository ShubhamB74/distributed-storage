"""baseline (infrastructure only)

Revision ID: 0001
Revises:
Create Date: 2026-11-17

"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Intentionally empty.

    Phase 0 only establishes migration tooling and records a baseline revision.
    Domain tables arrive in Phase 1, after the data model is approved.
    """


def downgrade() -> None:
    """Nothing to undo: the baseline creates no objects."""
