# Configuration

All settings are environment variables with the prefix `DISTRIBUTED_STORAGE_` (see
`src/distributed_storage/core/config.py`). A local `.env` file is read in development.

| Variable | Default | Notes |
|---|---|---|
| `DISTRIBUTED_STORAGE_ENV` | **required** | `dev`, `test` or `prod` |
| `DISTRIBUTED_STORAGE_DB_PASSWORD` | **required** | Non-empty; at least 16 characters in `prod` |
| `DISTRIBUTED_STORAGE_DB_PASSWORD_FILE` | none | Path to a file holding the password; used only if the plain variable is unset |
| `DISTRIBUTED_STORAGE_SERVICE_NAME` | `distributed-storage-api` | Included in every log line |
| `DISTRIBUTED_STORAGE_LOG_LEVEL` | `INFO` | `DEBUG` is rejected in `prod` |
| `DISTRIBUTED_STORAGE_DB_HOST` / `_PORT` / `_NAME` / `_USER` | `localhost` / `5432` / `distributed_storage` / `distributed_storage` | |
| `DISTRIBUTED_STORAGE_DB_POOL_SIZE` / `_MAX_OVERFLOW` | `5` / `5` | |
| `DISTRIBUTED_STORAGE_DB_CONNECT_TIMEOUT` | `5.0` | Seconds |
| `DISTRIBUTED_STORAGE_DB_ECHO` | `false` | SQL logging; rejected in `prod` |
| `DISTRIBUTED_STORAGE_READINESS_TIMEOUT` | `2.0` | Per-check timeout for `/readyz` |
| `DISTRIBUTED_STORAGE_ALEMBIC_CONFIG_PATH` | `alembic.ini` | Used to learn the expected migration head |

## Rules

- Required secrets have no defaults: the process refuses to start without them.
- Secrets are never printed: `repr`, `str` and validation errors mask them.
- Do not commit `.env`. `.env.example` must never contain real values.
- Production secrets come from the environment or mounted files (`*_FILE`), not from the image.
