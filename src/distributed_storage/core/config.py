"""Typed, environment-driven configuration.

Design rules:
- Required secrets have no defaults, so the application fails closed.
- Secrets are ``SecretStr`` and never appear in ``repr``/``str``/validation errors.
- - Any secret ``X`` may be supplied as ``DISTRIBUTED_STORAGE_X`` or as a path in
  ``DISTRIBUTED_STORAGE_X_FILE`` (for Docker/Kubernetes mounted secrets).
  The plain variable wins when both are set.
"""

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ENV_PREFIX = "DISTRIBUTED_STORAGE_"

# Fields that may be loaded from a file referenced by DISTRIBUTED_STORAGE_<FIELD>_FILE.
FILE_SECRET_FIELDS: tuple[str, ...] = ("db_password",)

MIN_PROD_DB_PASSWORD_LENGTH = 16


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    # Required: no defaults (fail closed).
    env: Environment
    db_password: SecretStr

    service_name: str = "distributed-storage-api"
    log_level: LogLevel = LogLevel.INFO

    db_host: str = "localhost"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "distributed_storage"
    db_user: str = "distributed_storage"
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_connect_timeout: float = Field(default=5.0, gt=0)
    db_echo: bool = False

    readiness_timeout: float = Field(default=2.0, gt=0)
    alembic_config_path: Path = Path("alembic.ini")

    @model_validator(mode="before")
    @classmethod
    def _load_file_secrets(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        merged = dict(data)
        for name in FILE_SECRET_FIELDS:
            if merged.get(name) not in (None, ""):
                continue
            file_var = f"{ENV_PREFIX}{name.upper()}_FILE"
            path = os.environ.get(file_var)
            if not path:
                continue
            try:
                merged[name] = Path(path).read_text(encoding="utf-8").rstrip("\r\n")
            except OSError as exc:
                # Name the variable, never the file content.
                raise ValueError(f"cannot read the secret file referenced by {file_var}") from exc
        return merged

    @field_validator("db_password")
    @classmethod
    def _password_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        if self.env is Environment.PROD:
            if self.db_echo:
                raise ValueError("db_echo must be disabled in prod")
            if self.log_level is LogLevel.DEBUG:
                raise ValueError("log_level DEBUG is not allowed in prod")
            if len(self.db_password.get_secret_value()) < MIN_PROD_DB_PASSWORD_LENGTH:
                raise ValueError(
                    f"db_password must be at least {MIN_PROD_DB_PASSWORD_LENGTH} characters in prod"
                )
        return self

    @classmethod
    def load(cls, **overrides: Any) -> Self:
        """Build settings from the environment (the one place we instantiate)."""
        return cls(**overrides)

    @property
    def is_prod(self) -> bool:
        return self.env is Environment.PROD

    @property
    def database_url(self) -> URL:
        """SQLAlchemy URL (password included: do not log or print this object)."""
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    def with_database(self, name: str) -> Self:
        return self.model_copy(update={"db_name": name})


@lru_cache
def get_settings() -> Settings:
    return Settings.load()
