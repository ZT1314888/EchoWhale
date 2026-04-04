from datetime import datetime, timezone

from pydantic import BaseModel, Field

from api.common.enums import MediaUploadStatus


class Media(BaseModel):
    id: str
    user_id: str
    filename: str
    content_type: str
    file_size: int
    storage_key: str
    upload_status: MediaUploadStatus = MediaUploadStatus.pending
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = Field(default_factory=list)


class MediaAccessGrant(BaseModel):
    media_id: str
    read_url: str
    expires_at: datetime


class MediaUploadResult(BaseModel):
    media: Media
    preview_url: str
    preview_url_expires_at: datetime
