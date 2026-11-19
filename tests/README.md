# Tests

| Directory | Marker | Needs | Purpose |
|---|---|---|---|
| `unit/` | `unit` | nothing | Fast logic tests; the environment is scrubbed of `DISTRIBUTED_STORAGE_*` |
| `integration/` | `integration` | PostgreSQL | Real database, never SQLite; one throwaway database per test |
| `fault/` | `fault` | varies | Fault injection (empty until the storage engine exists) |

Markers are applied automatically from the directory; `--strict-markers` rejects unknown ones.

```bash
make test-unit
make db-up && make test-integration
```

## Integration database

Fixtures (`tests/integration/conftest.py`) read connection settings from `.env` or the
environment, connect to the maintenance database, create `distributed_storage_test_<random>` and drop it
afterwards. Locally, tests skip with instructions when PostgreSQL is unreachable. When `CI` is set
they **fail** instead, so a broken pipeline cannot pass by skipping.

Migrations run in a subprocess because Alembic's async environment uses `asyncio.run`.
If the suite grows, switch to a pre-migrated template database for speed.

## Conventions

- Never depend on the developer's shell: unit tests clear `DISTRIBUTED_STORAGE_*` variables.
- Deterministic seeds for anything random. Property-based tests (Hypothesis) arrive with
  Phases 3 and 4, when there is logic worth fuzzing.
- Fault-injection tests will inject failures at named coordinator state transitions.
