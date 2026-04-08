from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from functools import lru_cache
import logging
import smtplib
from typing import Protocol

from api.common.exceptions import EmailDeliveryError
from api.core.config import settings
from api.models.user_model import User


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AuthMailDelivery:
    kind: str
    user_id: str
    email: str
    token: str | None = None
    code: str | None = None
    reset_url: str | None = None


class AuthMailer(Protocol):
    def send_verification_email(self, *, user: User, code: str) -> None: ...

    def send_password_reset_email(self, *, user: User, reset_url: str) -> None: ...


class NullAuthMailer:
    def send_verification_email(self, *, user: User, code: str) -> None:
        return None

    def send_password_reset_email(self, *, user: User, reset_url: str) -> None:
        return None


class RecordedAuthMailer:
    def __init__(self) -> None:
        self.deliveries: list[AuthMailDelivery] = []

    def send_verification_email(self, *, user: User, code: str) -> None:
        self.deliveries.append(
            AuthMailDelivery(
                kind="email_verification",
                user_id=user.id,
                email=user.email,
                code=code,
            )
        )

    def send_password_reset_email(self, *, user: User, reset_url: str) -> None:
        self.deliveries.append(
            AuthMailDelivery(
                kind="password_reset",
                user_id=user.id,
                email=user.email,
                reset_url=reset_url,
            )
        )


class SmtpAuthMailer:
    def __init__(self) -> None:
        self._host = settings.auth_smtp_host
        self._port = settings.auth_smtp_port
        self._username = settings.auth_smtp_username
        self._password = settings.auth_smtp_password
        self._from_email = settings.auth_smtp_from_email
        self._from_name = settings.auth_smtp_from_name
        self._use_ssl = settings.auth_smtp_use_ssl
        self._use_starttls = settings.auth_smtp_use_starttls

    def send_verification_email(self, *, user: User, code: str) -> None:
        message = EmailMessage()
        message["Subject"] = "EchoWhale 邮箱验证码"
        message["From"] = self._format_sender()
        message["To"] = user.email
        message.set_content(
            "\n".join(
                [
                    f"Hi {user.nickname},",
                    "",
                    "你的 EchoWhale 邮箱验证码如下：",
                    "",
                    code,
                    "",
                    f"验证码 {settings.auth_email_code_ttl_seconds // 60} 分钟内有效，重发后旧验证码会立即失效。",
                ]
            )
        )
        self._send_message(message)

    def send_password_reset_email(self, *, user: User, reset_url: str) -> None:
        message = EmailMessage()
        message["Subject"] = "EchoWhale 密码重置"
        message["From"] = self._format_sender()
        message["To"] = user.email
        message.set_content(
            "\n".join(
                [
                    f"Hi {user.nickname},",
                    "",
                    "你刚刚发起了密码重置请求。",
                    "请点击下面的链接完成密码重置：",
                    "",
                    reset_url,
                ]
            )
        )
        self._send_message(message)

    def _send_message(self, message: EmailMessage) -> None:
        smtp_cls = smtplib.SMTP_SSL if self._use_ssl else smtplib.SMTP
        try:
            with smtp_cls(self._host, self._port, timeout=30) as smtp_client:
                if self._use_starttls and not self._use_ssl:
                    smtp_client.starttls()
                if self._username.strip():
                    smtp_client.login(self._username, self._password)
                smtp_client.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning("SMTP authentication failed for sender %s", self._from_email)
            raise EmailDeliveryError("邮件服务认证失败，请检查 SMTP 配置") from exc
        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            logger.warning("SMTP delivery failed for sender %s: %s", self._from_email, exc)
            raise EmailDeliveryError() from exc

    def _format_sender(self) -> str:
        if self._from_name.strip():
            return f"{self._from_name} <{self._from_email}>"
        return self._from_email


@lru_cache
def get_auth_mailer() -> AuthMailer:
    if settings.auth_smtp_host.strip() and settings.auth_smtp_from_email.strip():
        return SmtpAuthMailer()
    return NullAuthMailer()
