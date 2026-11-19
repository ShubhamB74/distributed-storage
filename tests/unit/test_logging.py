import io
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from distributed_storage.core.logging import (
    REDACTED,
    JsonFormatter,
    configure_logging,
    correlation_id_var,
    is_sensitive_key,
    redact,
    request_id_var,
)


@pytest.fixture
def stream_logger() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(service="test-svc", env="test"))
    logger = logging.getLogger("distributed_storage.test.logging")
    logger.handlers[:] = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    yield logger, stream
    logger.handlers.clear()


def _emit(logger: logging.Logger, stream: io.StringIO, **extra: Any) -> dict[str, Any]:
    logger.info("something_happened", extra=extra)
    parsed: dict[str, Any] = json.loads(stream.getvalue().strip().splitlines()[-1])
    return parsed


def test_output_is_valid_json_with_standard_fields(
    stream_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = stream_logger
    record = _emit(logger, stream, node_id=7)
    assert record["event"] == "something_happened"
    assert record["level"] == "INFO"
    assert record["service"] == "test-svc"
    assert record["env"] == "test"
    assert record["timestamp"].endswith("+00:00")
    assert record["fields"] == {"node_id": 7}


def test_request_and_correlation_ids_are_included(
    stream_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = stream_logger
    request_token = request_id_var.set("req-1")
    correlation_token = correlation_id_var.set("corr-1")
    try:
        record = _emit(logger, stream)
    finally:
        request_id_var.reset(request_token)
        correlation_id_var.reset(correlation_token)
    assert record["request_id"] == "req-1"
    assert record["correlation_id"] == "corr-1"


def test_sensitive_fields_are_masked_including_nested(
    stream_logger: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = stream_logger
    record = _emit(
        logger,
        stream,
        password="hunter2",
        headers={"Authorization": "Bearer abc", "x-request-id": "ok"},
        items=[{"api_key": "k"}, {"name": "visible"}],
        accessToken="t",
    )
    raw = stream.getvalue()
    for leaked in ("hunter2", "Bearer abc", "abc", '"k"'):
        assert leaked not in raw.replace("[REDACTED]", "")
    fields = record["fields"]
    assert fields["password"] == REDACTED
    assert fields["headers"]["Authorization"] == REDACTED
    assert fields["headers"]["x-request-id"] == "ok"
    assert fields["items"][0]["api_key"] == REDACTED
    assert fields["items"][1]["name"] == "visible"
    assert fields["accessToken"] == REDACTED


def test_raw_bytes_are_never_logged(stream_logger: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = stream_logger
    record = _emit(logger, stream, blob=b"\x00\x01secretbytes", shard=bytearray(b"abc"))
    assert record["fields"]["blob"] == "<13 bytes>"
    assert record["fields"]["shard"] == "<3 bytes>"
    assert "secretbytes" not in stream.getvalue()


def test_exceptions_are_serialised(stream_logger: tuple[logging.Logger, io.StringIO]) -> None:
    logger, stream = stream_logger
    try:
        raise ValueError("boom")
    except ValueError:
        logger.warning("failed", exc_info=True)
    record = json.loads(stream.getvalue().strip())
    assert "ValueError: boom" in record["exception"]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("password", True),
        ("Authorization", True),
        ("x-api-key", True),
        ("accessToken", True),
        ("wrapped_key", True),
        ("DEK", True),
        ("ciphertext", True),
        ("user_id", False),
        ("node_id", False),
        ("idempotency_key", False),
        ("tokenizer_name", False),
    ],
)
def test_is_sensitive_key(key: str, expected: bool) -> None:
    assert is_sensitive_key(key) is expected


def test_redact_does_not_mutate_input() -> None:
    original = {"password": "x", "nested": {"token": "y"}}
    redacted = redact(original)
    assert original == {"password": "x", "nested": {"token": "y"}}
    assert redacted == {"password": REDACTED, "nested": {"token": REDACTED}}


def test_configure_logging_replaces_handlers_and_emits_json() -> None:
    stream = io.StringIO()
    configure_logging(level="INFO", service="svc", env="dev", stream=stream)
    configure_logging(level="INFO", service="svc", env="dev", stream=stream)  # idempotent
    assert len(logging.getLogger().handlers) == 1
    logging.getLogger("distributed_storage.test.configure").info("hello_world")
    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "hello_world"
