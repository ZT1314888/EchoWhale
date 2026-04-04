from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class Message(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    role: str
    text: str
    feedback: dict[str, object] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
