import pytest
from pydantic import ValidationError

from distributed_storage.core.config import Settings

LONG_PASSWORD = "a-long-enough-production-password-0123"


def test_phase1_defaults_are_safe(settings: Settings) -> None:
    assert settings.allow_registration is False
    assert settings.allow_dev_plaintext_upload is False
    assert settings.max_upload_bytes == 4 * 1024 * 1024
    assert settings.session_ttl_minutes == 720
    assert (settings.argon2_time_cost, settings.argon2_memory_cost_kib) == (3, 65536)


def test_dev_plaintext_upload_cannot_be_enabled_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "prod")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", LONG_PASSWORD)
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ALLOW_DEV_PLAINTEXT_UPLOAD", "true")
    with pytest.raises(ValidationError):
        Settings.load(_env_file=None)


def test_dev_plaintext_upload_is_allowed_outside_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", LONG_PASSWORD)
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ALLOW_DEV_PLAINTEXT_UPLOAD", "true")
    assert Settings.load(_env_file=None).allow_dev_plaintext_upload is True


def test_node_failure_thresholds_must_be_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", LONG_PASSWORD)
    monkeypatch.setenv("DISTRIBUTED_STORAGE_NODE_FAILURES_TO_SUSPECT", "6")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_NODE_FAILURES_TO_DOWN", "5")
    with pytest.raises(ValidationError):
        Settings.load(_env_file=None)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MAX_UPLOAD_BYTES", "0"),
        ("MAX_UPLOAD_BYTES", str(65 * 1024 * 1024)),
        ("SESSION_TTL_MINUTES", "0"),
        ("ARGON2_MEMORY_COST_KIB", "4"),
        ("LOGIN_MAX_FAILURES", "0"),
    ],
)
def test_out_of_range_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv("DISTRIBUTED_STORAGE_ENV", "dev")
    monkeypatch.setenv("DISTRIBUTED_STORAGE_DB_PASSWORD", LONG_PASSWORD)
    monkeypatch.setenv(f"DISTRIBUTED_STORAGE_{name}", value)
    with pytest.raises(ValidationError):
        Settings.load(_env_file=None)
