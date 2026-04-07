from pydantic import BaseModel, Field

from api.models.message_model import Message


class CoachReplyInput(BaseModel):
    scene: str
    role: str
    learner_message: str
    visual_anchors: list[str] = Field(default_factory=list)
    vocab_candidates: list[str] = Field(default_factory=list)
    recent_messages: list[Message] = Field(default_factory=list)


class CoachReplyResult(BaseModel):
    text: str
