# Database and migrations

- PostgreSQL via SQLAlchemy 2.x (async) and `asyncpg` (ADR-0013).
- Alembic runs with an async `env.py`; the URL comes from `Settings`, never from `alembic.ini`.
- The constraint/index naming convention lives in `distributed_storage/db/base.py`. It must not change
  once tables exist.
- Revision `0001` is an intentionally empty baseline. **No domain tables are created until the
  Phase 1 data model is approved.**

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
