"""Structured JSON logging with redaction of sensitive fields.

Convention: log an ``event`` name in snake_case as the message and put data in ``extra``:

    logger.info("shard_stored", extra={"node_id": node_id, "bytes": size})

Everything in ``extra`` is emitted under ``fields`` and passed through :func:`redact`.
Free-text messages and exception messages are NOT redacted: never interpolate secrets,
keys, plaintext or ciphertext into them.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

REDACTED = "[REDACTED]"

_SENSITIVE_TOKENS = frozenset(
    {
        "password",
        "passwd",
        "passphrase",
        "secret",
        "token",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "ciphertext",
        "plaintext",
        "apikey",
        "dek",
        "kek",
    }
)
_SENSITIVE_PHRASES = (
    "private_key",
    "api_key",
    "secret_key",
    "wrapped_key",
    "key_material",
    "session_key",
    "encryption_key",
)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")

_STANDARD_ATTRS = frozenset(
    vars(logging.LogRecord("x", 0, "x", 0, "", (), None)),
) | {"message", "asctime", "taskName"}


def is_sensitive_key(key: str) -> bool:
    normalized = _NON_ALNUM.sub("_", _CAMEL_BOUNDARY.sub("_", key).lower()).strip("_")
    if any(part in _SENSITIVE_TOKENS for part in normalized.split("_")):
        return True
    return any(phrase in normalized for phrase in _SENSITIVE_PHRASES)


def redact(value: Any, key: str | None = None) -> Any:
    """Return a log-safe copy of ``value``: sensitive keys masked, raw bytes summarised."""
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact(item) for item in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(value)} bytes>"
    return value


class JsonFormatter(logging.Formatter):
    def __init__(self, *, service: str, env: str) -> None:
        super().__init__()
        self._service = service
        self._env = env

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "service": self._service,
            "env": self._env,
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        correlation_id = correlation_id_var.get()
        if correlation_id:
            payload["correlation_id"] = correlation_id

        fields = {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        if fields:
            payload["fields"] = redact(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(*, level: str, service: str, env: str, stream: TextIO | None = None) -> None:
    """Route all logging (including uvicorn's) to one JSON handler on stdout."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(JsonFormatter(service=service, env=env))

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
    # Access logs include query strings (possible tokens); we log requests ourselves.
    logging.getLogger("uvicorn.access").disabled = True
