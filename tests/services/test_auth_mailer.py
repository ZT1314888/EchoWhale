from __future__ import annotations

import smtplib
from typing import Self

import pytest

from api.common.exceptions import EchoWhaleError
from api.models.user_model import User
from api.services import auth_mailer
from api.services.auth_mailer import SmtpAuthMailer


def _build_user() -> User:
    return User(
        id="user_123",
        email="learner@example.com",
        nickname="Echo Learner",
    )


def _configure_smtp_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_mailer.settings, "auth_smtp_host", "smtpdm.aliyun.com")
    monkeypatch.setattr(auth_mailer.settings, "auth_smtp_port", 465)
    monkeypatch.setattr(auth_mailer.settings, "auth_smtp_username", "noreply@example.com")
    monkeypatch.setattr(auth_mailer.settings, "auth_smtp_password", "smtp-password")
    monkeypatch.setattr(auth_mailer.settings, "auth_smtp_from_email", "noreply@example.com")
    monkeypatch.setattr(auth_mailer.settings, "auth_smtp_from_name", "EchoWhale")
    monkeypatch.setattr(auth_mailer.settings, "auth_smtp_use_ssl", True)
    monkeypatch.setattr(auth_mailer.settings, "auth_smtp_use_starttls", False)
    monkeypatch.setattr(auth_mailer.settings, "auth_email_code_ttl_seconds", 600)


def test_send_verification_email_translates_smtp_authentication_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_smtp_settings(monkeypatch)

    class FakeSmtpClient:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self) -> Self:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"Authentication failure")

        def send_message(self, message) -> None:
            raise AssertionError("send_message should not be called after auth failure")

    monkeypatch.setattr(auth_mailer.smtplib, "SMTP_SSL", FakeSmtpClient)

    mailer = SmtpAuthMailer()

    with pytest.raises(EchoWhaleError, match="邮件服务认证失败") as exc_info:
        mailer.send_verification_email(user=_build_user(), code="123456")

    assert exc_info.value.status_code == 503


def test_send_verification_email_translates_smtp_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_smtp_settings(monkeypatch)

    class FakeSmtpClient:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self) -> Self:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            return None

        def send_message(self, message) -> None:
            raise smtplib.SMTPServerDisconnected("server disconnected")

    monkeypatch.setattr(auth_mailer.smtplib, "SMTP_SSL", FakeSmtpClient)

    mailer = SmtpAuthMailer()

    with pytest.raises(EchoWhaleError, match="邮件服务暂时不可用") as exc_info:
        mailer.send_verification_email(user=_build_user(), code="123456")

    assert exc_info.value.status_code == 503


def test_send_password_reset_email_contains_reset_link_instead_of_raw_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_smtp_settings(monkeypatch)
    monkeypatch.setattr(auth_mailer.settings, "frontend_public_base_url", "https://app.example.com")
    captured: dict[str, object] = {}

    class FakeSmtpClient:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self) -> Self:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def login(self, username: str, password: str) -> None:
            return None

        def send_message(self, message) -> None:
            captured["message"] = message

    monkeypatch.setattr(auth_mailer.smtplib, "SMTP_SSL", FakeSmtpClient)

    mailer = SmtpAuthMailer()

    mailer.send_password_reset_email(
        user=_build_user(),
        reset_url="https://app.example.com/reset-password?token=reset-token",
    )

    message = captured["message"]
    content = message.get_content()
    assert "https://app.example.com/reset-password?token=reset-token" in content
    assert "请点击下面的链接完成密码重置：" in content
    assert "请使用下面的重置 token 完成后续操作：" not in content
