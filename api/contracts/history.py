from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from api.contracts.sessions import SessionReviewResponse
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.session_engine.review_builder import resolve_role_label, resolve_scene_title


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
    def from_session(cls, session: Session, review: SessionReviewResponse) -> HistoryEntryResponse:
        # 展示名与 SessionResponse 同一 resolver 语义（design 2.3）：此处此前用
        # 单参 get_scene_title（不带 role 组合），统一为三参后行为收敛——未知
        # 场景历史条目也展示"场景 · 角色 情景对话"组合与 LLM 值。
        return cls(
            id=session.id,
            practiced_at=_format_practiced_at(session.updated_at),
            status=_format_status(session),
            scene_title=resolve_scene_title(session.scene, session.role, session.llm_scene_title),
            role_label=resolve_role_label(session.scene, session.role, session.llm_role_label),
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
    # 与 SessionResponse 对齐（F17）：历史详情的 session 元数据块也下发展示文案，
    # 前端历史详情不再需要本地映射；未命中预设时回退为自然语言组合。
    scene_title: str
    role_label: str
    opener: str
    status: str
    visual_anchors: list[str]
    vocab_candidates: list[str]
    total_messages: int

    @classmethod
    def from_session(cls, session: Session, *, total_messages: int) -> HistorySessionMetaResponse:
        return cls(
            session_id=session.id,
            media_id=session.media_id,
            scene=session.scene,
            role=session.role,
            scene_title=resolve_scene_title(session.scene, session.role, session.llm_scene_title),
            role_label=resolve_role_label(session.scene, session.role, session.llm_role_label),
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
    def from_message(cls, message: Message) -> HistoryReplayMessageResponse:
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
