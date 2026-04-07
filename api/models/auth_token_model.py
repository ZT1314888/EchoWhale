from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


AUTH_TOKEN_PURPOSE_EMAIL_VERIFICATION = "email_verification"
AUTH_TOKEN_PURPOSE_PASSWORD_RESET = "password_reset"


class AuthActionTokenModel(BaseModel):
    id: str
    user_id: str
    purpose: str
    token_hash: str
    expires_at: datetime
    consumed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
