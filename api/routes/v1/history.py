from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.common.deps import require_authenticated_user
from api.common.ownership import build_user_owner
from api.common.responses import ApiResponse
from api.models.user_model import User
from api.models.session_model import Session
from api.modules.session_engine.review_builder import get_role_label, get_scene_title
from api.modules.session_engine.service import SessionEngineService
from api.routes.v1.sessions import SessionResponse, SessionReviewResponse, get_session_service


router = APIRouter(prefix="/history", tags=["history"])


class HistoryEntryResponse(BaseModel):
    id: str
    practiced_at: str
    status: str
    scene_title: str
    role_label: str
    preview: str
    tags: list[str]
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
            tags=list(session.labels),
            review_title=review.title,
            review_summary=review.next_try,
        )


class HistoryDetailResponse(BaseModel):
    entry: HistoryEntryResponse
    session: SessionResponse
    review: SessionReviewResponse


@router.get("/sessions", response_model=ApiResponse[list[HistoryEntryResponse]])
def list_history_sessions(
    session_service: SessionEngineService = Depends(get_session_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    sessions = session_service.list_history_sessions(build_user_owner(current_user.id))
    reviews = {
        session.id: SessionReviewResponse.from_review(
            session_service.get_session_review(session.id)
        )
        for session in sessions
    }
    return ApiResponse.success(
        data=[
            HistoryEntryResponse.from_session(session, reviews[session.id])
            for session in sessions
        ]
    )


@router.get("/sessions/{session_id}", response_model=ApiResponse[HistoryDetailResponse])
def get_history_session(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    current_user: User = Depends(require_authenticated_user),
) -> Any:
    session, review = session_service.get_history_session_detail(
        build_user_owner(current_user.id),
        session_id,
    )
    review_response = SessionReviewResponse.from_review(review)
    return ApiResponse.success(
        data=HistoryDetailResponse(
            entry=HistoryEntryResponse.from_session(session, review_response),
            session=SessionResponse.from_session(session),
            review=review_response,
        )
    )


def _format_practiced_at(updated_at: datetime) -> str:
    return updated_at.strftime("%Y-%m-%d %H:%M")


def _format_status(session: Session) -> str:
    learner_turns = sum(1 for message in session.messages if message.role == "user")
    return f"已完成 {learner_turns} 轮"
