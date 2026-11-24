"""Shared FastAPI dependencies."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from distributed_storage.api.errors import ApiError
from distributed_storage.core.config import Settings

DEV_ONLY_HEADER = "X-Development-Only"
DEV_ONLY_VALUE = "plaintext-storage"


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_settings_from_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_app)]


def require_dev_plaintext(request: Request, response: Response) -> None:
    """Phase 1's only upload path is development-only plaintext storage (no zero-knowledge)."""
    settings: Settings = request.app.state.settings
    if not settings.allow_dev_plaintext_upload:
        raise ApiError(404, "not_found", "resource not found")
    response.headers[DEV_ONLY_HEADER] = DEV_ONLY_VALUE
