from __future__ import annotations

from api.models.user_model import User
from api.services.auth_mailer import AuthMailDelivery
from api.services.auth_mailer import SmtpAuthMailer


def send_verification_email_task(*, delivery: dict[str, object] | AuthMailDelivery) -> None:
    normalized = _coerce_delivery(delivery)
    if normalized.code is None:
        raise ValueError("Verification delivery code is required")
    SmtpAuthMailer().send_verification_email(
        user=_build_user(normalized),
        code=normalized.code,
    )


def send_password_reset_email_task(*, delivery: dict[str, object] | AuthMailDelivery) -> None:
    normalized = _coerce_delivery(delivery)
    if normalized.reset_url is None:
        raise ValueError("Password reset delivery URL is required")
    SmtpAuthMailer().send_password_reset_email(
        user=_build_user(normalized),
        reset_url=normalized.reset_url,
    )


def _coerce_delivery(delivery: dict[str, object] | AuthMailDelivery) -> AuthMailDelivery:
    if isinstance(delivery, AuthMailDelivery):
        return delivery
    return AuthMailDelivery(**delivery)


def _build_user(delivery: AuthMailDelivery) -> User:
    return User(
        id=delivery.user_id,
        email=delivery.email,
        nickname=delivery.nickname or delivery.email,
    )
