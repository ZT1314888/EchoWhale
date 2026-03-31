from pydantic import BaseModel, Field

from api.common.enums import SessionStatus
from api.models.message_model import Message


class Session(BaseModel):
    id: str
    user_id: str
    media_id: str
    scene: str
    role: str
    opener: str
    status: SessionStatus = SessionStatus.active
    labels: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
