# syntax=docker/dockerfile:1

# uv image reference is overridable. TODO(Phase 0 follow-up): pin to a specific version/digest
# after the first successful build, matching the uv version used to generate uv.lock.
ARG PYTHON_VERSION=3.12
ARG UV_IMAGE=ghcr.io/astral-sh/uv:latest

FROM ${UV_IMAGE} AS uv

FROM python:${PYTHON_VERSION}-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv

# Dependencies first (cached unless pyproject/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Then the project itself, installed non-editable so the runtime image needs no sources.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:${PYTHON_VERSION}-slim AS runtime
RUN groupadd --system --gid 10001 distributed_storage \
    && useradd --system --uid 10001 --gid distributed_storage --no-create-home \
       --shell /usr/sbin/nologin distributed_storage
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /var/lib/distributed_storage/blobs \
    && chown -R 10001:10001 /var/lib/distributed_storage
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "--factory", "distributed_storage.api.main:create_app", \
     "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
