from pathlib import Path

import pytest
from pydantic import ValidationError

from distributed_storage.core.config import Environment, Settings

SECRET = "s3cr3t-value-xyz-0123456789"


def test_missing_password_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    with pytest.raises(ValidationError) as exc:
        Settings.load(_env_file=None)
    assert "db_password" in str(exc.value)


def test_missing_env_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", SECRET)
    with pytest.raises(ValidationError) as exc:
        Settings.load(_env_file=None)
    assert "env" in str(exc.value)


def test_invalid_env_value_rejected(valid_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "staging")
    with pytest.raises(ValidationError):
        Settings.load(_env_file=None)


def test_empty_password_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", "")
    with pytest.raises(ValidationError):
        Settings.load(_env_file=None)


def test_secret_is_masked_everywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", SECRET)
    loaded = Settings.load(_env_file=None)
    assert SECRET not in repr(loaded)
    assert SECRET not in str(loaded)
    assert SECRET not in repr(loaded.model_dump())
    assert loaded.db_password.get_secret_value() == SECRET


def test_validation_errors_do_not_echo_secret_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "prod")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", "short-pw")
    with pytest.raises(ValidationError) as exc:
        Settings.load(_env_file=None)
    assert "short-pw" not in str(exc.value)


def test_secret_loaded_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret_file = tmp_path / "db_password"
    secret_file.write_text(f"{SECRET}\n", encoding="utf-8")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD_FILE", str(secret_file))
    assert Settings.load(_env_file=None).db_password.get_secret_value() == SECRET


def test_plain_variable_wins_over_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret_file = tmp_path / "db_password"
    secret_file.write_text("from-file", encoding="utf-8")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", "from-env")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD_FILE", str(secret_file))
    assert Settings.load(_env_file=None).db_password.get_secret_value() == "from-env"


def test_unreadable_secret_file_fails_and_names_only_the_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD_FILE", str(tmp_path / "missing"))
    with pytest.raises(ValidationError) as exc:
        Settings.load(_env_file=None)
    assert "DISTRIBUTED_STORAGE_DB_PASSWORD_FILE" in str(exc.value)


def test_prod_rejects_short_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "prod")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", "too-short")
    with pytest.raises(ValidationError):
        Settings.load(_env_file=None)


def test_prod_rejects_db_echo_and_debug_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "prod")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", SECRET)
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_ECHO", "true")
    with pytest.raises(ValidationError):
        Settings.load(_env_file=None)
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_ECHO", "false")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_LOG_LEVEL", "DEBUG")
    with pytest.raises(ValidationError):
        Settings.load(_env_file=None)


def test_prod_accepts_valid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "prod")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", SECRET)
    loaded = Settings.load(_env_file=None)
    assert loaded.env is Environment.PROD
    assert loaded.is_prod


def test_database_url_escapes_special_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", "p@ss/w:rd")
    url = Settings.load(_env_file=None).database_url
    assert url.drivername == "postgresql+asyncpg"
    rendered = url.render_as_string(hide_password=False)
    assert "p%40ss%2Fw%3Ard" in rendered
    assert "p@ss/w:rd" not in url.render_as_string(hide_password=True)


def test_with_database_changes_only_the_name(settings: Settings) -> None:
    other = settings.with_database("other_db")
    assert other.db_name == "other_db"
    assert other.db_host == settings.db_host
    assert settings.db_name != "other_db"
