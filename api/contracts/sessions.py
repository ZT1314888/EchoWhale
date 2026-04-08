from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.session_model import Session
from api.modules.session_engine.schema import (
    LearnerMessagePayload,
    SampleSceneId,
    VoiceConversationTurn,
)


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
