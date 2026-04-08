from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.common.deps import require_authenticated_user
from api.common.ownership import build_user_owner
from api.common.responses import ApiResponse
from api.models.message_model import Message
from api.models.user_model import User
from api.models.session_model import Session
from api.modules.session_engine.review_builder import get_role_label, get_scene_title
from api.modules.session_engine.service import SessionEngineService
from api.routes.v1.sessions import SessionReviewResponse, get_session_service


router = APIRouter(prefix="/history", tags=["history"])


class HistoryEntryResponse(BaseModel):
    id: str
    practiced_at: str
    status: str
    scene_title: str
    role_label: str
    preview: str
    vocab_candidates: list[str]
    review_title: str
    review_summary: str

    @classmethod
    def from_session(cls, session: Session, review: SessionReviewResponse) -> "HistoryEntryResponse":
        return cls(
            id=session.id,
            practiced_at=_format_practiced_at(session.updated_at),
            status=_format_status(session),
            scene_title=get_scene_title(session.scene),
            role_label=get_role_label(session.scene, session.role),
            preview=review.highlight,
            vocab_candidates=list(session.vocab_candidates),
            review_title=review.title,
            review_summary=review.next_try,
        )


class HistoryDetailResponse(BaseModel):
    entry: HistoryEntryResponse
    session: HistorySessionMetaResponse
    review: SessionReviewResponse


class HistorySessionMetaResponse(BaseModel):
    session_id: str
    media_id: str | None
    scene: str
    role: str
    opener: str
    status: str
    visual_anchors: list[str]
    vocab_candidates: list[str]
    total_messages: int

    @classmethod
    def from_session(cls, session: Session, *, total_messages: int) -> "HistorySessionMetaResponse":
        return cls(
            session_id=session.id,
            media_id=session.media_id,
            scene=session.scene,
            role=session.role,
            opener=session.opener,
            status=session.status.value,
            visual_anchors=list(session.visual_anchors),
            vocab_candidates=list(session.vocab_candidates),
            total_messages=total_messages,
        )


class CursorPageResponse(BaseModel):
    has_more: bool
    next_cursor: str | None


class HistoryListResponse(BaseModel):
    items: list[HistoryEntryResponse]
    page: CursorPageResponse


class HistoryReplayMessageResponse(BaseModel):
    message_id: str
    role: str
    text: str

    @classmethod
    def from_message(cls, message: Message) -> "HistoryReplayMessageResponse":
        return cls(
            message_id=message.id,
            role=message.role,
            text=message.text,
        )


class HistoryReplayPageResponse(BaseModel):
    items: list[HistoryReplayMessageResponse]
    page: CursorPageResponse


@router.get("/sessions", response_model=ApiResponse[HistoryListResponse])
def list_history_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session_service: SessionEngineService = Depends(get_session_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    sessions, has_more, next_cursor = session_service.list_history_sessions_page(
        build_user_owner(current_user.id),
        limit=limit,
        cursor=cursor,
    )
    reviews = session_service.list_history_reviews([session.id for session in sessions])
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
def get_history_session(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    session, review, total_messages = session_service.get_history_session_overview(
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
def get_history_session_messages(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    session_service: SessionEngineService = Depends(get_session_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    messages, has_more, next_cursor = session_service.list_history_session_messages(
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


def _format_practiced_at(updated_at: datetime) -> str:
    return updated_at.strftime("%Y-%m-%d %H:%M")


def _format_status(session: Session) -> str:
    learner_turns = sum(1 for message in session.messages if message.role == "user")
    if learner_turns > 0:
        return f"已完成 {learner_turns} 轮"
    if session.status.value == "active":
        return "进行中"
    return "已完成"
