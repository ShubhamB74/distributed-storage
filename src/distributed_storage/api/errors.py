"""Uniform JSON errors (D18): {"error": {"code", "message", "request_id"?, "details"?}}.

Validation errors never echo the submitted input, because it may contain secrets.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from distributed_storage.core.logging import request_id_var

logger = logging.getLogger("distributed_storage.api")


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


def not_found() -> ApiError:
    return ApiError(404, "not_found", "resource not found")


def error_body(
    code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    request_id = request_id_var.get()
    if request_id:
        error["request_id"] = request_id
    if details:
        error["details"] = details
    return {"error": error}


async def _api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
        headers=exc.headers,
    )


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    details = [
        {"location": [str(part) for part in error["loc"]], "message": str(error["msg"])}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "the request is invalid", details),
    )


async def _http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(f"http_{exc.status_code}", str(exc.detail)),
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500, content=error_body("internal_error", "an internal error occurred")
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
