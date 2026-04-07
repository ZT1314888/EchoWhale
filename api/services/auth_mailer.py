from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from api.models.user_model import User


@dataclass(slots=True)
class AuthMailDelivery:
    kind: str
    user_id: str
    email: str
    token: str


class AuthMailer(Protocol):
    def send_verification_email(self, *, user: User, token: str) -> None: ...

    def send_password_reset_email(self, *, user: User, token: str) -> None: ...


class NullAuthMailer:
    def send_verification_email(self, *, user: User, token: str) -> None:
        return None

    def send_password_reset_email(self, *, user: User, token: str) -> None:
        return None


class RecordedAuthMailer:
    def __init__(self) -> None:
        self.deliveries: list[AuthMailDelivery] = []

    def send_verification_email(self, *, user: User, token: str) -> None:
        self.deliveries.append(
            AuthMailDelivery(
                kind="email_verification",
                user_id=user.id,
                email=user.email,
                token=token,
            )
        )

    def send_password_reset_email(self, *, user: User, token: str) -> None:
        self.deliveries.append(
            AuthMailDelivery(
                kind="password_reset",
                user_id=user.id,
                email=user.email,
                token=token,
            )
        )


@lru_cache
def get_auth_mailer() -> AuthMailer:
    return NullAuthMailer()
