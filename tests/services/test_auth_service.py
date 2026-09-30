from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from api.common.exceptions import AuthenticationError
from api.common.exceptions import PermissionDeniedError
from api.common.exceptions import TooManyRequestsError
from api.common.exceptions import ValidationError
from api.core.security import hash_password
from api.core.security import hash_refresh_token
from api.db.auth_db import SqlAlchemyAuthRepository
from api.db.database import create_all_tables, create_database_engine, create_session_factory
from api.models.user_model import User
from api.services.auth_service import AuthService


@dataclass
class FakeMailDelivery:
    kind: str
    user_id: str
    email: str
    nickname: str
    code: str | None = None
    reset_url: str | None = None


class FakeAuthMailQueuePublisher:
    def __init__(self) -> None:
        self.deliveries: list[FakeMailDelivery] = []
        self.raise_on_enqueue: Exception | None = None

    def enqueue_verification_email(
        self,
        *,
        user_id: str,
        email: str,
        nickname: str,
        code: str,
    ) -> None:
        if self.raise_on_enqueue is not None:
            raise self.raise_on_enqueue
        self.deliveries.append(
            FakeMailDelivery(
                kind="email_verification",
                user_id=user_id,
                email=email,
                nickname=nickname,
                code=code,
            )
        )

    def enqueue_password_reset_email(
        self,
        *,
        user_id: str,
        email: str,
        nickname: str,
        reset_url: str,
    ) -> None:
        if self.raise_on_enqueue is not None:
            raise self.raise_on_enqueue
        self.deliveries.append(
            FakeMailDelivery(
                kind="password_reset",
                user_id=user_id,
                email=email,
                nickname=nickname,
                reset_url=reset_url,
            )
        )


class FakeEmailVerificationStore:
    def __init__(self) -> None:
        self.next_code = "123456"
        self.codes: dict[str, str] = {}
        self.issue_calls: list[tuple[str, str]] = []
        self.block_issue = False

    def issue_code(self, *, email: str, ip_address: str) -> str:
        if self.block_issue:
            raise TooManyRequestsError("请求过于频繁")
        self.issue_calls.append((email, ip_address))
        self.codes[email] = self.next_code
        return self.next_code

    def consume_code(self, *, email: str, code: str) -> None:
        stored = self.codes.get(email)
        if stored != code:
            raise ValidationError("Verification code is invalid or expired")
        del self.codes[email]


def _build_service(
    database_path: Path,
    *,
    mail_queue_publisher: FakeAuthMailQueuePublisher | None = None,
    verification_store: FakeEmailVerificationStore | None = None,
) -> tuple[
    AuthService,
    SqlAlchemyAuthRepository,
    FakeAuthMailQueuePublisher,
    FakeEmailVerificationStore,
]:
    engine = create_database_engine(f"sqlite:///{database_path}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    create_all_tables(engine)
    repository = SqlAlchemyAuthRepository(create_session_factory(engine))
    active_mail_queue_publisher = mail_queue_publisher or FakeAuthMailQueuePublisher()
    active_verification_store = verification_store or FakeEmailVerificationStore()
    return (
        AuthService(
            repository=repository,
            mail_queue_publisher=active_mail_queue_publisher,
            verification_store=active_verification_store,
        ),
        repository,
        active_mail_queue_publisher,
        active_verification_store,
    )


def test_register_persists_user_without_issuing_session(tmp_path: Path) -> None:
    service, repository, publisher, verification_store = _build_service(tmp_path / "auth-register.db")

    user = service.register(
        nickname="Echo Learner",
        email="learner@example.com",
        password="secret123",
        ip_address="127.0.0.1",
    )

    assert user.email == "learner@example.com"
    stored_user = repository.get_user_by_email("learner@example.com")
    assert stored_user is not None
    assert stored_user.id == user.id
    assert stored_user.status == "pending_verification"
    assert len(publisher.deliveries) == 1
    assert publisher.deliveries[0].kind == "email_verification"
    assert publisher.deliveries[0].nickname == "Echo Learner"
    assert publisher.deliveries[0].code == "123456"
    assert verification_store.issue_calls == [("learner@example.com", "127.0.0.1")]


def test_register_normalizes_email_and_nickname_in_service(tmp_path: Path) -> None:
    service, repository, _, _ = _build_service(tmp_path / "auth-register-normalize.db")

    user = service.register(
        nickname="  Echo Learner  ",
        email="  Learner@Example.com  ",
        password="secret123",
        ip_address="127.0.0.1",
    )

    stored_user = repository.get_user_by_email("learner@example.com")
    assert user.email == "learner@example.com"
    assert user.nickname == "Echo Learner"
    assert stored_user is not None
    assert stored_user.email == "learner@example.com"
    assert stored_user.nickname == "Echo Learner"


def test_register_rejects_blank_nickname_in_service(tmp_path: Path) -> None:
    service, _, _, _ = _build_service(tmp_path / "auth-register-blank-nickname.db")

    with pytest.raises(ValidationError, match="Nickname is required"):
        service.register(
            nickname="   ",
            email="learner@example.com",
            password="secret123",
            ip_address="127.0.0.1",
        )


def test_register_rejects_invalid_email_format_in_service(tmp_path: Path) -> None:
    service, _, _, _ = _build_service(tmp_path / "auth-register-invalid-email.db")

    with pytest.raises(ValidationError, match="Invalid email format"):
        service.register(
            nickname="Echo Learner",
            email="not-an-email",
            password="secret123",
            ip_address="127.0.0.1",
        )


def test_login_rejects_wrong_password(tmp_path: Path) -> None:
    service, _, _, verification_store = _build_service(tmp_path / "auth-login.db")
    service.register(
        nickname="Echo Learner",
        email="learner@example.com",
        password="secret123",
        ip_address="127.0.0.1",
    )
    service.verify_email(email="learner@example.com", code=verification_store.next_code)

    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        service.login(email="learner@example.com", password="wrong-pass")


def test_login_rejects_pending_verification_user(tmp_path: Path) -> None:
    service, _, _, _ = _build_service(tmp_path / "auth-pending-login.db")
    service.register(
        nickname="Echo Learner",
        email="learner@example.com",
        password="secret123",
        ip_address="127.0.0.1",
    )

    with pytest.raises(PermissionDeniedError, match="Please verify your email before logging in"):
        service.login(email="learner@example.com", password="secret123")


def test_refresh_rotates_and_revokes_previous_refresh_token(tmp_path: Path) -> None:
    service, repository, _, verification_store = _build_service(tmp_path / "auth-refresh.db")
    service.register(
        nickname="Echo Learner",
        email="learner@example.com",
        password="secret123",
        ip_address="127.0.0.1",
    )
    service.verify_email(email="learner@example.com", code=verification_store.next_code)
    session = service.login(
        email="learner@example.com",
        password="secret123",
    )

    refreshed = service.refresh(refresh_token=session.refresh_token)

    revoked_token = repository.get_refresh_token(hash_refresh_token(session.refresh_token))
    active_token = repository.get_refresh_token(hash_refresh_token(refreshed.refresh_token))

    assert refreshed.access_token
    assert refreshed.refresh_token != session.refresh_token
    assert revoked_token is not None
    assert revoked_token.revoked_at is not None
    assert active_token is not None
    assert active_token.revoked_at is None


def test_login_rejects_disabled_user(tmp_path: Path) -> None:
    service, repository, _, _ = _build_service(tmp_path / "auth-disabled-login.db")
    repository.create_user(
        user=User(
            id="user_disabled",
            email="disabled@example.com",
            nickname="Disabled Learner",
            status="disabled",
        ),
        password_hash=hash_password("secret123"),
    )

    with pytest.raises(AuthenticationError, match="Authentication required"):
        service.login(email="disabled@example.com", password="secret123")


def test_verify_email_activates_user_and_consumes_token(tmp_path: Path) -> None:
    service, repository, publisher, verification_store = _build_service(tmp_path / "auth-verify-email.db")
    service.register(
        nickname="Echo Learner",
        email="learner@example.com",
        password="secret123",
        ip_address="127.0.0.1",
    )

    verification_code = publisher.deliveries[0].code
    verified_user = service.verify_email(email="learner@example.com", code=verification_code or "")
    stored_user = repository.get_user_by_email("learner@example.com")

    assert verified_user.status == "active"
    assert stored_user is not None
    assert stored_user.status == "active"
    assert "learner@example.com" not in verification_store.codes
    with pytest.raises(ValidationError, match="Verification code is invalid or expired"):
        service.verify_email(email="learner@example.com", code=verification_code or "")


def test_resend_verification_overwrites_previous_code(tmp_path: Path) -> None:
    service, _, publisher, verification_store = _build_service(tmp_path / "auth-resend.db")
    service.register(
        nickname="Echo Learner",
        email="learner@example.com",
        password="secret123",
        ip_address="127.0.0.1",
    )

    verification_store.next_code = "654321"

    service.resend_verification(email="learner@example.com", ip_address="127.0.0.1")

    assert verification_store.codes["learner@example.com"] == "654321"
    assert publisher.deliveries[-1].code == "654321"


def test_resend_verification_raises_when_frequency_limit_exceeded(tmp_path: Path) -> None:
    verification_store = FakeEmailVerificationStore()
    service, _, _, _ = _build_service(
        tmp_path / "auth-resend-rate-limit.db",
        verification_store=verification_store,
    )
    service.register(
        nickname="Echo Learner",
        email="learner@example.com",
        password="secret123",
        ip_address="127.0.0.1",
    )
    verification_store.block_issue = True

    with pytest.raises(TooManyRequestsError, match="请求过于频繁"):
        service.resend_verification(email="learner@example.com", ip_address="127.0.0.1")


def test_reset_password_rotates_credentials_and_revokes_existing_refresh_tokens(tmp_path: Path) -> None:
    service, repository, publisher, verification_store = _build_service(tmp_path / "auth-reset-password.db")
    service.register(
        nickname="Echo Learner",
        email="learner@example.com",
        password="secret123",
        ip_address="127.0.0.1",
    )
    service.verify_email(email="learner@example.com", code=verification_store.next_code)
    session = service.login(
        email="learner@example.com",
        password="secret123",
    )

    service.forgot_password(email="learner@example.com")
    reset_url = publisher.deliveries[-1].reset_url
    assert reset_url is not None
    parsed = urlparse(reset_url)
    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost:5173"
    assert parsed.path == "/reset-password"
    reset_token = parse_qs(parsed.query)["token"][0]
    service.reset_password(token=reset_token, password="renew1234")

    revoked_refresh = repository.get_refresh_token(hash_refresh_token(session.refresh_token))

    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        service.login(email="learner@example.com", password="secret123")

    renewed_session = service.login(email="learner@example.com", password="renew1234")

    assert revoked_refresh is not None
    assert revoked_refresh.revoked_at is not None
    assert renewed_session.access_token
    with pytest.raises(ValidationError, match="Password reset link is invalid or expired"):
        service.reset_password(token=reset_token, password="renew5678")


def test_register_translates_duplicate_email_conflict_into_validation_error() -> None:
    class DuplicateEmailRepository:
        def get_user_by_email(self, email: str):
            return None

        def create_user(self, *, user: User, password_hash: str) -> User:
            raise IntegrityError("duplicate email", params=None, orig=Exception("duplicate"))

    service = AuthService(repository=DuplicateEmailRepository())

    with pytest.raises(ValidationError, match="Email already registered"):
        service.register(
            nickname="Echo Learner",
            email="learner@example.com",
            password="secret123",
            ip_address="127.0.0.1",
        )


def test_register_raises_when_mail_job_cannot_be_enqueued(tmp_path: Path) -> None:
    publisher = FakeAuthMailQueuePublisher()
    publisher.raise_on_enqueue = ValidationError("queue unavailable")
    service, _, _, _ = _build_service(
        tmp_path / "auth-register-enqueue-failure.db",
        mail_queue_publisher=publisher,
    )

    with pytest.raises(ValidationError, match="queue unavailable"):
        service.register(
            nickname="Echo Learner",
            email="learner@example.com",
            password="secret123",
            ip_address="127.0.0.1",
        )
