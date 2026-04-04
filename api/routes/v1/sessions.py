from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.common.responses import ApiResponse
from api.core.config import settings
from api.db.media_db import build_media_repository
from api.db.session_db import build_session_repository
from api.integrations.storage.r2 import R2StorageService
from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.session_model import Session
from api.modules.session_engine.service import SessionEngineService
from api.modules.session_engine.schema import LearnerMessagePayload


router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionRequest(BaseModel):
    media_id: str


class SessionReplyRequest(LearnerMessagePayload):
    pass


class SessionMessageResponse(BaseModel):
    message_id: str
    role: str
    text: str
    feedback: dict[str, object] | None = None

    @classmethod
    def from_message(cls, message: Message) -> "SessionMessageResponse":
        return cls(
            message_id=message.id,
            role=message.role,
            text=message.text,
            feedback=message.feedback,
        )


class SessionResponse(BaseModel):
    session_id: str
    media_id: str
    scene: str
    role: str
    opener: str
    status: str
    labels: list[str]
    messages: list[SessionMessageResponse]

    @classmethod
    def from_session(cls, session: Session) -> "SessionResponse":
        return cls(
            session_id=session.id,
            media_id=session.media_id,
            scene=session.scene,
            role=session.role,
            opener=session.opener,
            status=session.status.value,
            labels=session.labels,
            messages=[SessionMessageResponse.from_message(message) for message in session.messages],
        )


class ReplyFeedbackResponse(BaseModel):
    grammar: str
    more_natural: str
    useful_words: list[str]


class FeedbackMetricResponse(BaseModel):
    title: str
    body: str


class UsefulWordsMetricResponse(BaseModel):
    title: str
    words: list[str]
    body: str


class PracticeFeedbackResponse(BaseModel):
    grammar: FeedbackMetricResponse
    more_natural: FeedbackMetricResponse
    useful_words: UsefulWordsMetricResponse
    next_step: FeedbackMetricResponse


class SessionReviewResponse(BaseModel):
    session_id: str
    title: str
    highlight: str
    next_try: str
    feedback: PracticeFeedbackResponse

    @classmethod
    def from_review(cls, review: SessionReview) -> "SessionReviewResponse":
        return cls(
            session_id=review.session_id,
            title=review.title,
            highlight=review.highlight,
            next_try=review.next_try,
            feedback=PracticeFeedbackResponse(
                grammar=FeedbackMetricResponse(
                    title=review.feedback.grammar.title,
                    body=review.feedback.grammar.body,
                ),
                more_natural=FeedbackMetricResponse(
                    title=review.feedback.more_natural.title,
                    body=review.feedback.more_natural.body,
                ),
                useful_words=UsefulWordsMetricResponse(
                    title=review.feedback.useful_words.title,
                    words=list(review.feedback.useful_words.words),
                    body=review.feedback.useful_words.body,
                ),
                next_step=FeedbackMetricResponse(
                    title=review.feedback.next_step.title,
                    body=review.feedback.next_step.body,
                ),
            ),
        )


class SessionReplyResponse(BaseModel):
    session: SessionResponse
    feedback: ReplyFeedbackResponse | None = None

    @classmethod
    def from_session(cls, session: Session) -> "SessionReplyResponse":
        feedback = None
        for message in reversed(session.messages):
            if message.feedback:
                feedback = ReplyFeedbackResponse(**message.feedback)
                break
        return cls(session=SessionResponse.from_session(session), feedback=feedback)


def get_session_service() -> SessionEngineService:
    return SessionEngineService(
        media_lookup=build_media_repository(),
        session_repository=build_session_repository(),
        read_url_signer=R2StorageService(),
    )


@router.post("", response_model=ApiResponse[SessionResponse])
def start_session(
    payload: StartSessionRequest,
    session_service: SessionEngineService = Depends(get_session_service),
) -> Any:
    session = session_service.start_session(
        user_id=settings.default_user_id,
        media_id=payload.media_id,
    )
    return ApiResponse.success(data=SessionResponse.from_session(session))


@router.get("/{session_id}", response_model=ApiResponse[SessionResponse])
def get_session(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
) -> Any:
    session = session_service.get_session(session_id)
    return ApiResponse.success(data=SessionResponse.from_session(session))


@router.post("/{session_id}/reply", response_model=ApiResponse[SessionReplyResponse])
def reply_to_session(
    session_id: str,
    payload: SessionReplyRequest,
    session_service: SessionEngineService = Depends(get_session_service),
) -> Any:
    session = session_service.reply_to_session(session_id, payload.learner_message)
    return ApiResponse.success(data=SessionReplyResponse.from_session(session))


@router.get("/{session_id}/review", response_model=ApiResponse[SessionReviewResponse])
def get_session_review(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
) -> Any:
    review = session_service.get_session_review(session_id)
    return ApiResponse.success(data=SessionReviewResponse.from_review(review))
