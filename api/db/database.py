from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.common.exceptions import ConfigurationError
from api.core.config import settings


class Base(DeclarativeBase):
    pass


SessionFactory = Callable[[], Session]


def create_database_engine(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


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


def create_all_tables(engine: Engine) -> None:
    import api.db.auth_db  # noqa: F401
    import api.db.media_db  # noqa: F401
    import api.db.session_db  # noqa: F401

    Base.metadata.create_all(bind=engine)
