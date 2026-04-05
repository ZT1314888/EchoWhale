from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class User(BaseModel):
    id: str
    email: str
    nickname: str
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def name(self) -> str:
        return self.nickname


class RefreshTokenRecordModel(BaseModel):
    id: str
    user_id: str
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class VisitorIdentity(BaseModel):
    id: str
