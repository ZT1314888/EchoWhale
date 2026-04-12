from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.common.exceptions import ConfigurationError
from api.core.config import settings


class Base(DeclarativeBase):
    pass


SessionFactory = Callable[[], Session]
AsyncSessionFactory = Callable[[], AsyncSession]


def create_database_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        engine_kwargs.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            pool_recycle=settings.database_pool_recycle_seconds,
        )

    return create_engine(database_url, **engine_kwargs)


def create_session_factory(engine: Engine) -> SessionFactory:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory


@lru_cache
def get_database_engine() -> Engine:
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL is not configured")
    return create_database_engine(settings.database_url)


@lru_cache
def get_session_factory() -> SessionFactory:
    return create_session_factory(get_database_engine())


def create_async_database_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if database_url.startswith("sqlite"):
        if database_url.startswith("sqlite://"):
            database_url = database_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        connect_args["check_same_thread"] = False
    else:
        engine_kwargs.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            pool_recycle=settings.database_pool_recycle_seconds,
        )

    return create_async_engine(database_url, **engine_kwargs)


def create_async_session_factory(engine: AsyncEngine) -> AsyncSessionFactory:
    factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=AsyncSession)
    return factory


@lru_cache
def get_async_database_engine() -> AsyncEngine:
    if not settings.database_url:
        raise ConfigurationError("DATABASE_URL is not configured")
    return create_async_database_engine(settings.database_url)


@lru_cache
def get_async_session_factory() -> AsyncSessionFactory:
    return create_async_session_factory(get_async_database_engine())


def create_all_tables(engine: Engine) -> None:
    import api.db.auth_db  # noqa: F401
    import api.db.media_db  # noqa: F401
    import api.db.session_db  # noqa: F401

    Base.metadata.create_all(bind=engine)
