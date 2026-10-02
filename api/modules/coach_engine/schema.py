from pydantic import BaseModel, Field

from api.models.message_model import Message


class CoachReplyInput(BaseModel):
    scene: str
    role: str
    learner_message: str
    visual_anchors: list[str] = Field(default_factory=list)
    vocab_candidates: list[str] = Field(default_factory=list)
    recent_messages: list[Message] = Field(default_factory=list)
    # 学员档案注入（只加可选字段，契约零破坏）：learner_context 是服务端渲染
    # 的有界注入块（封闭集合值 + 整数，无学习者原文），learner_cefr 是档案
    # 滚动估计（A1..C2），覆盖系统提示词水平行；两者缺省即回退静态注入。
    learner_context: str | None = None
    learner_cefr: str | None = None


class CoachReplyResult(BaseModel):
    text: str
