"""Request/correlation ID propagation and access logging (pure ASGI)."""

import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from distributed_storage.core.logging import correlation_id_var, request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"

# Client-supplied correlation IDs are accepted only if they are short and boring,
# which prevents log injection and oversized values.
_CORRELATION_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")

logger = logging.getLogger("distributed_storage.http")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # The request ID is always generated server-side; clients cannot choose it.
        request_id = uuid4().hex
        incoming = Headers(scope=scope).get(CORRELATION_ID_HEADER)
        if incoming and _CORRELATION_ID_PATTERN.fullmatch(incoming):
            correlation_id = incoming
        else:
            correlation_id = request_id

        request_token = request_id_var.set(request_id)
        correlation_token = correlation_id_var.set(correlation_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_ids(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                headers[CORRELATION_ID_HEADER] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_ids)
        finally:
            logger.info(
                "http_request_completed",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],  # no query string: it may carry tokens
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            request_id_var.reset(request_token)
            correlation_id_var.reset(correlation_token)
