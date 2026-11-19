"""Async engine construction (SQLAlchemy 2.x + asyncpg)."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from distributed_storage.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    # Engine creation is lazy: no connection is made until first use, so the API can
    # start while PostgreSQL is briefly unavailable (readiness reports the truth).
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={"timeout": settings.db_connect_timeout},
    )
