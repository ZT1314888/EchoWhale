from fastapi import Header

from api.core.config import settings
from api.models.user_model import User


def get_current_user(x_demo_user: str | None = Header(default=None)) -> User:
    user_id = x_demo_user or settings.default_user_id
    return User(id=user_id, name=settings.default_user_name)
