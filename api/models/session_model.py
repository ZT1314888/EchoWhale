from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator

from api.common.enums import SessionStatus
from api.models.message_model import Message


class Session(BaseModel):
    id: str
    user_id: str
    media_id: str | None
    scene: str
    role: str
    opener: str
    status: SessionStatus = SessionStatus.active
    visual_anchors: list[str] = Field(default_factory=list)
    vocab_candidates: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def fill_compatibility_labels(self) -> "Session":
        if self.labels and not self.vocab_candidates and not self.visual_anchors:
            self.vocab_candidates = list(self.labels)

        combined = []
        seen: set[str] = set()
        for value in [*self.visual_anchors, *self.vocab_candidates]:
            if value in seen:
                continue
            seen.add(value)
            combined.append(value)
        self.labels = combined or list(self.labels)
        return self
