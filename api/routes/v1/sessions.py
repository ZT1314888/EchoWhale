from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi import status as fastapi_status
from fastapi.responses import StreamingResponse

from api.common.deps import ResourceOwnerContext, apply_visitor_cookie, get_resource_owner
from api.common.exceptions import EchoWhaleError
from api.common.responses import ApiResponse
from api.contracts.sessions import (
    SessionReplyRequest,
    SessionReplyResponse,
    SessionResponse,
    SessionReviewResponse,
    SessionStartPendingResponse,
    StartSessionRequest,
    VoiceBootstrapResponse,
    VoiceCompleteRequest,
    VoiceCompleteResponse,
)
from api.db.media_db import build_media_repository
from api.db.session_db import build_session_repository
from api.integrations.storage.r2 import R2StorageService
from api.modules.session_engine.schema import SceneAnalysisPending
from api.modules.session_engine.service import SessionEngineService
from api.services.llm_rate_limit import (
    LLMRateLimiter,
    consume_with_ip_guard,
    get_llm_rate_limiter,
)

logger = logging.getLogger(__name__)


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
    request: Request,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
    rate_limiter: LLMRateLimiter = Depends(get_llm_rate_limiter),
) -> Any:
    # 先消耗 visitor 键再消耗 IP 键：任一超限即 429，visitor 先报保持既有语义。
    consume_with_ip_guard(
        rate_limiter,
        action="session_start",
        ip_action="session_start_ip",
        owner=owner,
        request=request,
    )
    result = await session_service.start_session(
        user_id=owner.owner_id,
        media_id=payload.media_id,
        sample_scene_id=payload.sample_scene_id,
    )
    if isinstance(result, SceneAnalysisPending):
        # 缓存未命中且已转异步分析：202 + 状态挂起载荷，客户端轮询后重试 start。
        response = ApiResponse.success(
            data=SessionStartPendingResponse(status=result.status, media_id=result.media_id),
            http_code=fastapi_status.HTTP_202_ACCEPTED,
        )
    else:
        response = ApiResponse.success(data=SessionResponse.from_session(result))
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
    request: Request,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
    rate_limiter: LLMRateLimiter = Depends(get_llm_rate_limiter),
) -> Any:
    # 先 visitor 后 IP，与 start_session 的消耗顺序保持一致。
    consume_with_ip_guard(
        rate_limiter,
        action="reply",
        ip_action="reply_ip",
        owner=owner,
        request=request,
    )
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
            session_id=(
                bootstrap["session_id"] if isinstance(bootstrap, dict) else bootstrap.session_id
            ),
            deepgram_access_token=(
                bootstrap["deepgram_access_token"]
                if isinstance(bootstrap, dict)
                else bootstrap.deepgram_access_token
            ),
            expires_in=(
                bootstrap["expires_in"] if isinstance(bootstrap, dict) else bootstrap.expires_in
            ),
            deepgram_ws_url=(
                bootstrap["deepgram_ws_url"]
                if isinstance(bootstrap, dict)
                else bootstrap.deepgram_ws_url
            ),
            agent_settings=(
                bootstrap["agent_settings"]
                if isinstance(bootstrap, dict)
                else bootstrap.agent_settings
            ),
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


@router.post("/{session_id}/reply/stream")
async def stream_reply_to_session(
    session_id: str,
    payload: SessionReplyRequest,
    request: Request,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
    rate_limiter: LLMRateLimiter = Depends(get_llm_rate_limiter),
) -> Any:
    """SSE 版文字回复：先回执 feedback，再逐 token 下发 coach 回复。

    鉴权/限流/404 等前置校验全部发生在开流之前，错误仍走统一信封；
    开流后的任何失败以 error 事件下发（信封同构，无 HTTP 状态码可改）。
    """
    # 先 visitor 后 IP，与 start_session 的消耗顺序保持一致。
    consume_with_ip_guard(
        rate_limiter,
        action="reply",
        ip_action="reply_ip",
        owner=owner,
        request=request,
    )
    event_stream = await session_service.prepare_reply_stream(
        session_id,
        payload.learner_message,
        owner_id=owner.owner_id,
    )
    response = StreamingResponse(
        _reply_sse_events(event_stream),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    apply_visitor_cookie(response=response, owner=owner)
    return response


async def _reply_sse_events(
    event_stream: AsyncIterator[tuple[str, object]],
) -> AsyncIterator[str]:
    """把 agent 事件流编码成 SSE 帧；异常收敛为 error 事件（失败轮次不落库）。"""
    try:
        async for event_name, event_payload in event_stream:
            if event_name == "delta":
                data: dict[str, object] = {"text": event_payload}
            elif event_name == "feedback":
                data = event_payload.model_dump()
            elif event_name == "session":
                data = SessionReplyResponse.from_session(event_payload).model_dump()
            else:  # pragma: no cover - 防御未知事件类型
                continue
            yield _encode_sse_event(event_name, data)
    except EchoWhaleError as exc:
        logger.warning("reply_stream_business_error code=%s message=%s", exc.code, exc.message)
        yield _encode_sse_event(
            "error",
            {"code": exc.code, "message": exc.message, "data": exc.data},
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("reply_stream_unexpected_error")
        yield _encode_sse_event(
            "error",
            {"code": 1005, "message": "Internal server error", "data": None},
        )


def _encode_sse_event(event_name: str, data: dict[str, object]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
