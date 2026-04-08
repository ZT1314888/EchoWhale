from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from api.common.deps import ResourceOwnerContext, apply_visitor_cookie, get_resource_owner
from api.common.responses import ApiResponse
from api.db.media_db import build_media_repository
from api.db.session_db import build_session_repository
from api.integrations.storage.r2 import R2StorageService
from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.session_model import Session
from api.modules.session_engine.service import SessionEngineService
from api.modules.session_engine.schema import (
    LearnerMessagePayload,
    SampleSceneId,
    VoiceConversationTurn,
)


router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionRequest(BaseModel):
    media_id: str | None = None
    sample_scene_id: SampleSceneId | None = None

    @model_validator(mode="after")
    def validate_start_source(self) -> "StartSessionRequest":
        has_media = self.media_id is not None
        has_sample = self.sample_scene_id is not None
        if has_media == has_sample:
            raise ValueError("Exactly one of media_id or sample_scene_id is required")
        return self


class SessionReplyRequest(LearnerMessagePayload):
    pass


class VoiceCompleteRequest(BaseModel):
    conversation: list[VoiceConversationTurn]
    termination_reason: str = "user_ended"
    client_diagnostics: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_voice_conversation(self) -> "VoiceCompleteRequest":
        if not self.conversation:
            raise ValueError("Conversation cannot be empty")
        if not any(turn.role == "user" for turn in self.conversation):
            raise ValueError("Conversation must include at least one user turn")
        return self


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
    media_id: str | None
    scene: str
    role: str
    opener: str
    status: str
    visual_anchors: list[str]
    vocab_candidates: list[str]
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
            visual_anchors=list(session.visual_anchors),
            vocab_candidates=list(session.vocab_candidates),
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


class VoiceBootstrapResponse(BaseModel):
    session_id: str
    deepgram_access_token: str
    expires_in: float
    deepgram_ws_url: str
    agent_settings: dict[str, object]
    session: SessionResponse


class VoiceCompleteResponse(BaseModel):
    session: SessionResponse
    review: SessionReviewResponse


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
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    session = session_service.start_session(
        user_id=owner.owner_id,
        media_id=payload.media_id,
        sample_scene_id=payload.sample_scene_id,
    )
    response = ApiResponse.success(data=SessionResponse.from_session(session))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.get("/{session_id}", response_model=ApiResponse[SessionResponse])
def get_session(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    session = session_service.get_session(session_id, owner_id=owner.owner_id)
    response = ApiResponse.success(data=SessionResponse.from_session(session))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.post("/{session_id}/reply", response_model=ApiResponse[SessionReplyResponse])
def reply_to_session(
    session_id: str,
    payload: SessionReplyRequest,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    session = session_service.reply_to_session(
        session_id,
        payload.learner_message,
        owner_id=owner.owner_id,
    )
    response = ApiResponse.success(data=SessionReplyResponse.from_session(session))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.get("/{session_id}/review", response_model=ApiResponse[SessionReviewResponse])
def get_session_review(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    review = session_service.get_session_review(session_id, owner_id=owner.owner_id)
    response = ApiResponse.success(data=SessionReviewResponse.from_review(review))
    apply_visitor_cookie(response=response, owner=owner)
    return response


@router.post("/{session_id}/voice/bootstrap", response_model=ApiResponse[VoiceBootstrapResponse])
def bootstrap_voice_session(
    session_id: str,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    bootstrap = session_service.bootstrap_voice_session(session_id, owner_id=owner.owner_id)
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
def complete_voice_session(
    session_id: str,
    payload: VoiceCompleteRequest,
    session_service: SessionEngineService = Depends(get_session_service),
    owner: ResourceOwnerContext = Depends(get_resource_owner),
) -> Any:
    result = session_service.complete_voice_session(
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
