from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from api.common.deps import require_authenticated_user
from api.common.ownership import build_user_owner
from api.common.responses import ApiResponse
from api.contracts.history import (
    CursorPageResponse,
    HistoryDetailResponse,
    HistoryEntryResponse,
    HistoryListResponse,
    HistoryReplayMessageResponse,
    HistoryReplayPageResponse,
    HistorySessionMetaResponse,
)
from api.contracts.sessions import SessionReviewResponse
from api.models.user_model import User
from api.modules.session_engine.service import SessionEngineService
from api.routes.v1.sessions import get_session_service


router = APIRouter(prefix="/history", tags=["history"])


@router.get("/sessions", response_model=ApiResponse[HistoryListResponse])
async def list_history_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session_service: SessionEngineService = Depends(get_session_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    sessions, has_more, next_cursor = await session_service.list_history_sessions_page(
        build_user_owner(current_user.id),
        limit=limit,
        cursor=cursor,
    )
    reviews = await session_service.list_history_reviews([session.id for session in sessions])
    items = [
        HistoryEntryResponse.from_session(
            session,
            SessionReviewResponse.from_review(reviews[session.id]),
        )
        for session in sessions
        if session.id in reviews
    ]
    return ApiResponse.success(
        data=HistoryListResponse(
            items=items,
            page=CursorPageResponse(has_more=has_more, next_cursor=next_cursor),
        )
    )


@router.get("/sessions/{session_id}", response_model=ApiResponse[HistoryDetailResponse])
async def get_history_session(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    session, review, total_messages = await session_service.get_history_session_overview(
        build_user_owner(current_user.id),
        session_id,
    )
    review_response = SessionReviewResponse.from_review(review)
    return ApiResponse.success(
        data=HistoryDetailResponse(
            entry=HistoryEntryResponse.from_session(session, review_response),
            session=HistorySessionMetaResponse.from_session(
                session,
                total_messages=total_messages,
            ),
            review=review_response,
        )
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=ApiResponse[HistoryReplayPageResponse],
)
async def get_history_session_messages(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session_service: SessionEngineService = Depends(get_session_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    messages, has_more, next_cursor = await session_service.list_history_session_messages(
        build_user_owner(current_user.id),
        session_id,
        limit=limit,
        cursor=cursor,
    )
    return ApiResponse.success(
        data=HistoryReplayPageResponse(
            items=[HistoryReplayMessageResponse.from_message(message) for message in messages],
            page=CursorPageResponse(has_more=has_more, next_cursor=next_cursor),
        )
    )
