from __future__ import annotations

from pydantic import BaseModel

from api.models.user_model import User


class AuthSession(BaseModel):
    access_token: str
    refresh_token: str
    user: User
