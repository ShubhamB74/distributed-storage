# Distributed Storage

Zero-knowledge, fault-tolerant distributed file storage, built phase by phase.

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker with Compose v2

## Quick start

```bash
make setup      # uv sync (first run creates uv.lock: commit it)
make env        # creates .env with a generated database password
make hooks      # optional: install pre-commit hooks
make check      # lint, types, unit tests (no Docker needed)

make db-up      # start PostgreSQL via Docker Compose
make test-integration
make up         # full stack: postgres -> migrate -> api
make smoke      # liveness, readiness, outage and recovery checks
make down       # stop and delete volumes
```

API: <http://127.0.0.1:8000/healthz> (liveness) and `/readyz` (readiness).

## Layout

```
src/distributed_storage/   api/ (app factory, health, middleware), core/ (config, logging), db/ (engine, base)
migrations/      Alembic (async) environment and versions
tests/           unit/ integration/ fault/   (see tests/README.md)
docs/            architecture, ADRs, configuration, database, logging, data-model drafts
scripts/         gen-dev-env.sh, smoke-compose.sh
```

More: [docs/dev-environment.md](docs/dev-environment.md) | [CONTRIBUTING.md](CONTRIBUTING.md)
