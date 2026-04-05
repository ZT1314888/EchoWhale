from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from api.common.deps import ResourceOwnerContext, apply_visitor_cookie, get_resource_owner
from api.common.responses import ApiResponse
from api.core.config import settings
from api.db.media_db import build_media_repository
from api.integrations.storage.r2 import R2StorageService
from api.models.media_model import Media, MediaAccessGrant, MediaUploadResult
from api.services.media_service import MediaService


router = APIRouter(prefix="/media", tags=["media"])


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


def get_media_service() -> MediaService:
    return MediaService(
        storage=R2StorageService(),
        repository=build_media_repository(),
        max_file_size=settings.media_max_file_size,
        signed_url_ttl_seconds=settings.r2_signed_url_ttl_seconds,
        allowed_content_types=tuple(settings.media_allowed_content_types),
    )


@router.post("/upload", response_model=ApiResponse[MediaResponse])
async def upload_media(
    file: UploadFile = File(...),
    media_service: MediaService = Depends(get_media_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    result = media_service.upload_media(
        user_id=owner.owner_id,
        filename=file.filename or "upload",
        content_type=file.content_type or "",
        content=await file.read(),
    )
    response = ApiResponse.success(data=MediaResponse.from_upload_result(result))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.get("/{media_id}", response_model=ApiResponse[MediaResponse])
def get_media(
    media_id: str,
    media_service: MediaService = Depends(get_media_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    media = media_service.get_media(media_id, owner_id=owner.owner_id)
    response = ApiResponse.success(data=MediaResponse.from_media(media))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.get("/{media_id}/access-url", response_model=ApiResponse[MediaAccessResponse])
def get_media_access_url(
    media_id: str,
    media_service: MediaService = Depends(get_media_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    access = media_service.create_media_access_url(media_id, owner_id=owner.owner_id)
    response = ApiResponse.success(data=MediaAccessResponse.from_access_grant(access))
    apply_visitor_cookie(response=response, owner=owner)
    return response
