from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from api.contracts.sessions import SessionReviewResponse
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.session_engine.review_builder import get_role_label, get_scene_title


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


class HistoryDetailResponse(BaseModel):
    entry: HistoryEntryResponse
    session: HistorySessionMetaResponse
    review: SessionReviewResponse


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


def _format_practiced_at(updated_at: datetime) -> str:
    return updated_at.strftime("%Y-%m-%d %H:%M")


def _format_status(session: Session) -> str:
    learner_turns = sum(1 for message in session.messages if message.role == "user")
    if learner_turns > 0:
        return f"已完成 {learner_turns} 轮"
    if session.status.value == "active":
        return "进行中"
    return "已完成"
