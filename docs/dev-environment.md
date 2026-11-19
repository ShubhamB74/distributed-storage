# Development environment

## Setup

```bash
make setup   # uv sync; the first run generates uv.lock, which must be committed
make env     # .env from .env.example with a generated DB password (mode 600)
```

`.env` is git-ignored and is read both by the application (host runs) and by Docker Compose.
Compose refuses to start if `DISTRIBUTED_STORAGE_DB_USER`, `DISTRIBUTED_STORAGE_DB_NAME` or `DISTRIBUTED_STORAGE_DB_PASSWORD`
is missing or empty.

## Stack (Docker Compose)

| Service | Purpose |
|---|---|
| `postgres` | PostgreSQL 16 (pinned major), named volume, healthcheck, published on 127.0.0.1 only |
| `migrate` | One-shot `alembic upgrade head`; not a worker |
| `api` | FastAPI app, non-root user, read-only filesystem, all capabilities dropped |

No worker or storage-node containers exist yet (decision D10; storage nodes arrive in Phase 4).

## Typical flows

- Unit tests only: `make check` (no Docker).
- Integration tests: `make db-up && make test-integration`. Each test creates and drops its own
  database, so the development database is never touched.
- Full stack: `make up && make smoke`.

## Known follow-ups

- Pin the uv image in the `Dockerfile` (`UV_IMAGE`) to the version used to create `uv.lock`.
- Pin GitHub Actions to commit SHAs (Dependabot will keep them current).
- Compose containers on one host are *simulated* failure domains for later phases.
