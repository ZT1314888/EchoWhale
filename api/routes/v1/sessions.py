from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.common.deps import ResourceOwnerContext, apply_visitor_cookie, get_resource_owner
from api.common.responses import ApiResponse
from api.contracts.sessions import (
    SessionReplyRequest,
    SessionReplyResponse,
    SessionResponse,
    SessionReviewResponse,
    StartSessionRequest,
    VoiceBootstrapResponse,
    VoiceCompleteRequest,
    VoiceCompleteResponse,
)
from api.db.media_db import build_media_repository
from api.db.session_db import build_session_repository
from api.integrations.storage.r2 import R2StorageService
from api.modules.session_engine.service import SessionEngineService


router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_session_service() -> SessionEngineService:
    return SessionEngineService(
        media_lookup=build_media_repository(),
        session_repository=build_session_repository(),
        read_url_signer=R2StorageService(),
    )


@router.post("", response_model=ApiResponse[SessionResponse])
async def start_session(
    payload: StartSessionRequest,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    session = await session_service.start_session(
        user_id=owner.owner_id,
        media_id=payload.media_id,
        sample_scene_id=payload.sample_scene_id,
    )
    response = ApiResponse.success(data=SessionResponse.from_session(session))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.get("/{session_id}", response_model=ApiResponse[SessionResponse])
async def get_session(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    session = await session_service.get_session(session_id, owner_id=owner.owner_id)
    response = ApiResponse.success(data=SessionResponse.from_session(session))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.post("/{session_id}/reply", response_model=ApiResponse[SessionReplyResponse])
async def reply_to_session(
    session_id: str,
    payload: SessionReplyRequest,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    session = await session_service.reply_to_session(
        session_id,
        payload.learner_message,
        owner_id=owner.owner_id,
    )
    response = ApiResponse.success(data=SessionReplyResponse.from_session(session))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.get("/{session_id}/review", response_model=ApiResponse[SessionReviewResponse])
async def get_session_review(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    review = await session_service.get_session_review(session_id, owner_id=owner.owner_id)
    response = ApiResponse.success(data=SessionReviewResponse.from_review(review))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.post("/{session_id}/voice/bootstrap", response_model=ApiResponse[VoiceBootstrapResponse])
async def bootstrap_voice_session(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    bootstrap = await session_service.bootstrap_voice_session(session_id, owner_id=owner.owner_id)
    response = ApiResponse.success(
        data=VoiceBootstrapResponse(
            session_id=bootstrap["session_id"] if isinstance(bootstrap, dict) else bootstrap.session_id,
            deepgram_access_token=bootstrap["deepgram_access_token"]
            if isinstance(bootstrap, dict)
            else bootstrap.deepgram_access_token,
            expires_in=bootstrap["expires_in"] if isinstance(bootstrap, dict) else bootstrap.expires_in,
            deepgram_ws_url=bootstrap["deepgram_ws_url"]
            if isinstance(bootstrap, dict)
            else bootstrap.deepgram_ws_url,
            agent_settings=bootstrap["agent_settings"] if isinstance(bootstrap, dict) else bootstrap.agent_settings,
            session=SessionResponse.from_session(
                bootstrap["session"] if isinstance(bootstrap, dict) else bootstrap.session
            ),
        )
    )
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.post("/{session_id}/voice/complete", response_model=ApiResponse[VoiceCompleteResponse])
async def complete_voice_session(
    session_id: str,
    payload: VoiceCompleteRequest,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    result = await session_service.complete_voice_session(
        session_id=session_id,
        conversation=payload.conversation,
        termination_reason=payload.termination_reason,
        client_diagnostics=payload.client_diagnostics,
        owner_id=owner.owner_id,
    )
    response = ApiResponse.success(
        data=VoiceCompleteResponse(
            session=SessionResponse.from_session(
                result["session"] if isinstance(result, dict) else result.session
            ),
            review=SessionReviewResponse.from_review(
                result["review"] if isinstance(result, dict) else result.review
            ),
        )
    )
    apply_visitor_cookie(response=response, owner=owner)
    return response
