import os
from collections.abc import Iterator

import pytest

from distributed_storage.core.config import ENV_PREFIX, Settings


@pytest.fixture(autouse=True)
def _clean_distributed_storage_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Unit tests must not depend on the developer's shell or .env file."""
    for name in list(os.environ):
        if name.startswith(ENV_PREFIX):
            monkeypatch.delenv(name)
    yield


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", "unit-test-password-0123456789")


@pytest.fixture
def settings(valid_env: None) -> Settings:
    return Settings.load(_env_file=None)
