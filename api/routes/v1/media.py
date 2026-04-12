from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile

from api.common.deps import ResourceOwnerContext, apply_visitor_cookie, get_resource_owner
from api.common.responses import ApiResponse
from api.contracts.media import MediaAccessResponse, MediaResponse
from api.core.config import settings
from api.db.media_db import build_media_repository
from api.integrations.storage.r2 import R2StorageService
from api.services.media_service import MediaService


router = APIRouter(prefix="/media", tags=["media"])


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
    result = await media_service.upload_media(
        user_id=owner.owner_id,
        filename=file.filename or "upload",
        content_type=file.content_type or "",
        content=await file.read(),
    )
    response = ApiResponse.success(data=MediaResponse.from_upload_result(result))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.get("/{media_id}", response_model=ApiResponse[MediaResponse])
async def get_media(
    media_id: str,
    media_service: MediaService = Depends(get_media_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    media = await media_service.get_media(media_id, owner_id=owner.owner_id)
    response = ApiResponse.success(data=MediaResponse.from_media(media))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.get("/{media_id}/access-url", response_model=ApiResponse[MediaAccessResponse])
async def get_media_access_url(
    media_id: str,
    media_service: MediaService = Depends(get_media_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    access = await media_service.create_media_access_url(media_id, owner_id=owner.owner_id)
    response = ApiResponse.success(data=MediaAccessResponse.from_access_grant(access))
    apply_visitor_cookie(response=response, owner=owner)
    return response
