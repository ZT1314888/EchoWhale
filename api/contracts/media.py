from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from api.models.media_model import Media, MediaAccessGrant, MediaUploadResult


class MediaResponse(BaseModel):
    media_id: str
    filename: str
    content_type: str
    file_size: int
    storage_key: str
    upload_status: str
    preview_url: str | None = None
    preview_url_expires_at: datetime | None = None

    @classmethod
    def from_media(
        cls,
        media: Media,
        *,
        preview_url: str | None = None,
        preview_url_expires_at: datetime | None = None,
    ) -> "MediaResponse":
        return cls(
            media_id=media.id,
            filename=media.filename,
            content_type=media.content_type,
            file_size=media.file_size,
            storage_key=media.storage_key,
            upload_status=media.upload_status.value,
            preview_url=preview_url,
            preview_url_expires_at=preview_url_expires_at,
        )

    @classmethod
    def from_upload_result(cls, result: MediaUploadResult) -> "MediaResponse":
        return cls.from_media(
            result.media,
            preview_url=result.preview_url,
            preview_url_expires_at=result.preview_url_expires_at,
        )


class MediaAccessResponse(BaseModel):
    media_id: str
    read_url: str
    expires_at: datetime

    @classmethod
    def from_access_grant(cls, grant: MediaAccessGrant) -> "MediaAccessResponse":
        return cls(
            media_id=grant.media_id,
            read_url=grant.read_url,
            expires_at=grant.expires_at,
        )
