# ADR-0013: Development tooling, database access and CI

- **Status:** Accepted (D7, D8, D9 approved 2026-11-17; PostgreSQL major version noted below is an implementer default)
- **Date:** 2026-11-17
- **Deciders:** project owner
- **Related:** D7, D8, D9, ADR-0004

## Context

Phase 0 must fix a minimal, reproducible toolchain without constraining later phases.

## Decision

- **Language/runtime:** Python 3.12.
- **Dependency and environment management:** `uv` (`pyproject.toml` + committed `uv.lock`).
- **Database access:** SQLAlchemy 2.x with its async API and the `asyncpg` driver. Alembic for
  migrations, using an async `env.py`.
- **CI:** GitHub Actions.
- **Integration tests:** real PostgreSQL only, never SQLite or other substitutes. Locally via
  Docker Compose; in CI via a PostgreSQL service container.
- **Quality tools (implementer defaults, not part of the approved list):** ruff, mypy (strict), pytest + pytest-asyncio, httpx.
- **PostgreSQL version (implementer default, confirm):** 16, pinned to the major version in Compose and CI.

## Alternatives considered

- Sync SQLAlchemy + psycopg: simpler tests, but diverges from the async API and from the approved stack.
- Poetry/pip-tools: viable; uv chosen by the owner for speed and a single tool.
- SQLite for integration tests: rejected; behaviour differs in locking, types and concurrency semantics that this project depends on.

## Consequences

- Alembic runs in a subprocess in tests because its async environment calls `asyncio.run`.
- asyncpg-specific behaviours (error types, timeouts) are part of the contract.
- `uv.lock` must be committed; CI and Docker use it frozen. The uv image and GitHub Actions are not yet pinned by digest/SHA (tracked follow-ups).

## Revisit when

A dependency becomes unmaintained, a Python or PostgreSQL version leaves support, or CI becomes a bottleneck.
