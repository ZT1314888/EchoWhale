from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import JSON, BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from api.common.enums import MediaUploadStatus
from api.common.exceptions import NotFoundError
from api.db.database import Base, SessionFactory, get_session_factory
from api.models.media_model import Media


class MediaLookup(Protocol):
    def get_media(self, media_id: str) -> Media: ...


class MediaRepository(MediaLookup, Protocol):
    def save_media(self, media: Media) -> Media: ...


class MediaRecord(Base):
    __tablename__ = "media"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    upload_status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)


class SqlAlchemyMediaRepository:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def save_media(self, media: Media) -> Media:
        with self._session_factory() as session:
            record = MediaRecord(
                id=media.id,
                user_id=media.user_id,
                filename=media.filename,
                content_type=media.content_type,
                file_size=media.file_size,
                storage_key=media.storage_key,
                upload_status=media.upload_status.value,
                created_at=media.created_at,
                tags=list(media.tags),
            )
            session.merge(record)
            session.commit()
        return media

    def get_media(self, media_id: str) -> Media:
        with self._session_factory() as session:
            record = session.get(MediaRecord, media_id)
            if record is None:
                raise NotFoundError(f"Media {media_id} not found")
            return _to_media(record)

    def reset(self) -> None:
        with self._session_factory() as session:
            session.query(MediaRecord).delete()
            session.commit()


def save_media(media: Media) -> Media:
    return SqlAlchemyMediaRepository().save_media(media)


def get_media(media_id: str) -> Media:
    return SqlAlchemyMediaRepository().get_media(media_id)


def reset_media_store() -> None:
    SqlAlchemyMediaRepository().reset()


def build_media_repository(session_factory: SessionFactory | None = None) -> MediaRepository:
    return SqlAlchemyMediaRepository(session_factory)


def _to_media(record: MediaRecord) -> Media:
    return Media(
        id=record.id,
        user_id=record.user_id,
        filename=record.filename,
        content_type=record.content_type,
        file_size=record.file_size,
        storage_key=record.storage_key,
        upload_status=MediaUploadStatus(record.upload_status),
        created_at=record.created_at,
        tags=list(record.tags or []),
    )
