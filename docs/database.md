# Database and migrations

- PostgreSQL via SQLAlchemy 2.x (async) and `asyncpg` (ADR-0013).
- Alembic runs with an async `env.py`; the URL comes from `Settings`, never from `alembic.ini`.
- The constraint/index naming convention lives in `distributed_storage/db/base.py`. It must not change
  once tables exist.
- Revision `0001` is an intentionally empty baseline.
- Revision `0002` creates the Phase 1 schema (see `docs/data-model/phase1-data-model.md`): users, devices,
  sessions, storage nodes, files, file versions, stripes, shard placements and audit events.
- Importing `distributed_storage.db.base` registers every model on `Base.metadata`, which Alembic's
  `env.py` and the drift test rely on.
- `audit_events` is insert-only: triggers reject `UPDATE`, `DELETE` and `TRUNCATE`. This is not tamper
  evidence, because a database owner can drop the triggers (hash chaining arrives in Phase 7).
- All foreign keys are `ON DELETE RESTRICT`; `files.current_version_id` is deferrable so a file and its
  first version can be inserted in one transaction.

## Commands

```bash
make migrate                                # alembic upgrade head
uv run alembic revision -m "message"        # new revision (autogenerate once models exist)
uv run alembic downgrade -1
```

## Policy

- Every migration has a working `downgrade`, verified by the CI cycle (upgrade, downgrade, upgrade).
- A drift test fails if models and migrations disagree.
- `/readyz` reports not-ready unless the database is at the expected single head.
