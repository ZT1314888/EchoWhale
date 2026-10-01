from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile

from api.common.deps import ResourceOwnerContext, apply_visitor_cookie, get_resource_owner
from api.common.exceptions import NotFoundError
from api.common.responses import ApiResponse
from api.contracts.media import MediaAccessResponse, MediaResponse, SceneAnalysisStatusResponse
from api.core.config import settings
from api.db.media_db import MediaRepository, build_media_repository
from api.db.scene_analysis_db import SceneAnalysisStore, build_scene_analysis_store
from api.integrations.storage.r2 import R2StorageService
from api.services.llm_rate_limit import (
    LLMRateLimiter,
    consume_with_ip_guard,
    get_llm_rate_limiter,
)
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
    request: Request,
    file: UploadFile = File(...),
    media_service: MediaService = Depends(get_media_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
    rate_limiter: LLMRateLimiter = Depends(get_llm_rate_limiter),
) -> Any:
    # 上传是无鉴权门槛的高成本端点：进流式校验前先限流——先 owner 键后
    # 匿名 IP 兜底键，429 语义与 sessions 端点一致（任务 prd R3）。
    consume_with_ip_guard(
        rate_limiter,
        action="media_upload",
        ip_action="media_upload_ip",
        owner=owner,
        request=request,
    )
    result = await media_service.upload_media(
        user_id=owner.owner_id,
        filename=file.filename or "upload",
        content_type=file.content_type or "",
        # file.file 是 SpooledTemporaryFile（>1MB 已落盘），直接交给流式
        # 校验与 storage 直传，全程不 .read() 进内存（任务 prd R2）。
        fileobj=file.file,
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


def get_media_repository() -> MediaRepository:
    return build_media_repository()


def get_scene_analysis_store() -> SceneAnalysisStore:
    return build_scene_analysis_store()


@router.get("/{media_id}/scene-analysis", response_model=ApiResponse[SceneAnalysisStatusResponse])
async def get_media_scene_analysis(
    media_id: str,
    owner: ResourceOwnerContext = Depends(get_resource_owner),
    media_repository: MediaRepository = Depends(get_media_repository),
    scene_store: SceneAnalysisStore = Depends(get_scene_analysis_store),
) -> Any:
    """场景分析缓存状态查询：start 返回 202 后客户端轮询此端点等待就绪。"""
    media = await media_repository.get_media(media_id)
    if media.user_id != owner.owner_id:
        # 归属校验与媒体访问一致：越权一律收敛成不存在，避免探测。
        raise NotFoundError(f"Media {media_id} not found")
    snapshot = await scene_store.get(media_id)
    if snapshot is None:
        status_payload = SceneAnalysisStatusResponse(media_id=media_id, status="unknown")
    else:
        status_payload = SceneAnalysisStatusResponse(
            media_id=media_id,
            status=snapshot.status,
            prompt_version=snapshot.prompt_version,
            scene=snapshot.scene,
            role=snapshot.role,
            confidence=snapshot.confidence,
            error_code=snapshot.error_code,
        )
    response = ApiResponse.success(data=status_payload)
    apply_visitor_cookie(response=response, owner=owner)
    return response
