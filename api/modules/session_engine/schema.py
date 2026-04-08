from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from api.models.review_model import SessionReview
from api.models.session_model import Session


SampleSceneId = Literal["coffee", "office", "street"]


class StartSessionInput(BaseModel):
    user_id: str
    media_id: str | None = None
    sample_scene_id: SampleSceneId | None = None

    @model_validator(mode="after")
    def validate_start_source(self) -> "StartSessionInput":
        has_media = self.media_id is not None
        has_sample = self.sample_scene_id is not None
        if has_media == has_sample:
            raise ValueError("Exactly one of media_id or sample_scene_id is required")
        return self


class LearnerMessagePayload(BaseModel):
    learner_message: str

    @field_validator("learner_message")
    @classmethod
    def normalize_learner_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Learner message cannot be empty")
        return normalized


class ReplyInput(LearnerMessagePayload):
    session_id: str


class VoiceConversationTurn(BaseModel):
    role: Literal["assistant", "user"]
    content: str

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Conversation content cannot be empty")
        return normalized


class VoiceCompleteInput(BaseModel):
    session_id: str
    conversation: list[VoiceConversationTurn] = Field(default_factory=list)
    termination_reason: str = "user_ended"
    client_diagnostics: dict[str, object] = Field(default_factory=dict)

    @field_validator("conversation")
    @classmethod
    def validate_conversation(cls, value: list[VoiceConversationTurn]) -> list[VoiceConversationTurn]:
        if not value:
            raise ValueError("Conversation cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_conversation_has_user_turn(self) -> "VoiceCompleteInput":
        if not any(turn.role == "user" for turn in self.conversation):
            raise ValueError("Conversation must include at least one user turn")
        return self


class VoiceBootstrapResult(BaseModel):
    session_id: str
    deepgram_access_token: str
    expires_in: float
    deepgram_ws_url: str
    agent_settings: dict[str, object]
    session: Session


class VoiceCompleteResult(BaseModel):
    session: Session
    review: SessionReview
