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
        """确保启动会话时只能二选一地传图片或样例场景。"""
        has_media = self.media_id is not None
        has_sample = self.sample_scene_id is not None
        if has_media == has_sample:
            raise ValueError("Exactly one of media_id or sample_scene_id is required")
        return self


class LearnerMessagePayload(BaseModel):
    # 长度硬顶（Finding 11）：超长输入会直接进 prompt 并撑大 Text 列；
    # 超限走 pydantic ValidationError → 现有 RequestValidationError 处理器。
    learner_message: str = Field(max_length=2000)

    @field_validator("learner_message")
    @classmethod
    def normalize_learner_message(cls, value: str) -> str:
        """去掉首尾空白，避免空消息进入对话链路。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Learner message cannot be empty")
        return normalized


class ReplyInput(LearnerMessagePayload):
    session_id: str


class SceneAnalysisPending(BaseModel):
    """media 路径未命中缓存且已入队异步分析时的挂起结果，客户端凭 media_id 轮询状态端点。"""

    media_id: str
    status: Literal["analyzing"] = "analyzing"


class VoiceConversationTurn(BaseModel):
    role: Literal["assistant", "user"]
    # 单条转写硬顶（Finding 11）：语音转写按 turn 入库，超长 turn 同样会撑大 Text 列。
    content: str = Field(max_length=4000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        """清理转写内容空白，确保每个语音 turn 都有有效文本。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Conversation content cannot be empty")
        return normalized


class VoiceCompleteInput(BaseModel):
    session_id: str
    # 转写条数硬顶（Finding 11）：无界 transcript 会让收口流程的写放大失去约束。
    conversation: list[VoiceConversationTurn] = Field(default_factory=list, max_length=200)
    termination_reason: str = "user_ended"
    client_diagnostics: dict[str, object] = Field(default_factory=dict)

    @field_validator("conversation")
    @classmethod
    def validate_conversation(
        cls, value: list[VoiceConversationTurn]
    ) -> list[VoiceConversationTurn]:
        """阻止空 transcript 进入语音收口流程。"""
        if not value:
            raise ValueError("Conversation cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_conversation_has_user_turn(self) -> "VoiceCompleteInput":
        """确保最终 transcript 至少包含一条学习者发言。"""
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
