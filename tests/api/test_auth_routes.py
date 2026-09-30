from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.common.exceptions import AuthenticationError
from api.common.exceptions import EchoWhaleError
from api.common.exceptions import QueuePublishError
from api.common.exceptions import TooManyRequestsError
from api.common.exceptions import ValidationError
from api.main import app
from api.models.auth_model import AuthSession
from api.models.user_model import User
from api.services.auth_rate_limit import get_auth_rate_limiter

try:
    from api.routes.v1.auth import get_auth_service
except ImportError:  # pragma: no cover - expected during red phase
    get_auth_service = None




def _authorization_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_payload(email: str = "learner@example.com") -> dict[str, str]:
    return {
        "nickname": "Echo Learner",
        "email": email,
        "password": "secret123",
    }


def _login_payload(email: str = "learner@example.com") -> dict[str, str]:
    return {
        "email": email,
        "password": "secret123",
    }


def _login_user(client: TestClient, email: str = "learner@example.com") -> tuple[dict, str]:
    register_response = client.post("/api/v1/auth/register", json=_register_payload(email))
    assert register_response.status_code == 200

    response = client.post("/api/v1/auth/login", json=_login_payload(email))
    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie
    return (response.json(), set_cookie.split(";", maxsplit=1)[0].split("=", maxsplit=1)[1])


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    if get_auth_service is not None:
        app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    app.dependency_overrides[get_auth_rate_limiter] = lambda: FakeAuthRateLimiter()

    with TestClient(app) as test_client:
        yield test_client


class FakeAuthService:
    def __init__(self) -> None:
        self.tokens = {"valid-access-token": "user_123"}
        self.reset_calls: list[tuple[str, str]] = []
        self.verification_codes: list[tuple[str, str]] = []
        self.forgot_password_emails: list[str] = []
        self.resend_verification_emails: list[str] = []
        self.raise_on_resend: Exception | None = None

    def register(self, *, nickname: str, email: str, password: str, ip_address: str):
        if not nickname.strip():
            raise ValidationError("Nickname is required")
        return User(id="user_123", email=email, nickname=nickname)

    def login(self, *, email: str, password: str):
        return AuthSession(
            access_token="valid-access-token",
            refresh_token="refresh-token-2",
            user=User(id="user_123", email=email, nickname="Echo Learner"),
        )

    def get_current_user(self, *, access_token: str):
        if access_token not in self.tokens:
            raise AuthenticationError("Authentication required")
        return User(id="user_123", email="learner@example.com", nickname="Echo Learner")

    def refresh(self, *, refresh_token: str):
        if not refresh_token:
            raise AuthenticationError("Authentication required")
        return AuthSession(
            access_token="valid-access-token-rotated",
            refresh_token="refresh-token-rotated",
            user=User(id="user_123", email="learner@example.com", nickname="Echo Learner"),
        )

    def logout(self, *, refresh_token: str) -> None:
        if not refresh_token:
            raise AuthenticationError("Authentication required")

    def resend_verification(self, *, email: str, ip_address: str) -> None:
        if self.raise_on_resend is not None:
            raise self.raise_on_resend
        self.resend_verification_emails.append(email)

    def verify_email(self, *, email: str, code: str) -> User:
        self.verification_codes.append((email, code))
        return User(id="user_123", email="learner@example.com", nickname="Echo Learner")

    def forgot_password(self, *, email: str) -> None:
        self.forgot_password_emails.append(email)

    def reset_password(self, *, token: str, password: str) -> None:
        self.reset_calls.append((token, password))


class FakeAuthRateLimiter:
    def __init__(self) -> None:
        self.blocked_action: str | None = None

    def consume(self, *, action: str, key: str) -> None:
        if action == self.blocked_action:
            raise TooManyRequestsError("Too many auth attempts")


def _fake_rate_limiter() -> FakeAuthRateLimiter:
    override = app.dependency_overrides[get_auth_rate_limiter]
    return override()


def test_register_creates_user_without_issuing_session(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=_register_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "Success"
    assert body["data"]["user_id"] == "user_123"
    assert body["data"]["email"] == "learner@example.com"
    assert body["data"]["nickname"] == "Echo Learner"
    assert response.headers.get("set-cookie") is None


def test_register_rejects_invalid_email_format(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "nickname": "Echo Learner",
            "email": "not-an-email",
            "password": "secret123",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
    assert response.json()["message"] == "Validation error"


def test_register_rejects_blank_nickname(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "nickname": "   ",
            "email": "learner@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
    assert response.json()["message"] == "Validation error"


def test_login_allows_existing_non_compliant_password_shape(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "learner@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["access_token"] == "valid-access-token"


def test_me_returns_authenticated_user_summary(client: TestClient) -> None:
    login_body, _ = _login_user(client)

    response = client.get(
        "/api/v1/auth/me",
        headers=_authorization_header(login_body["data"]["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["user_id"]
    assert body["data"]["email"] == "learner@example.com"
    assert body["data"]["nickname"] == "Echo Learner"


def test_refresh_rotates_access_token_from_cookie(client: TestClient) -> None:
    _, refresh_cookie = _login_user(client)
    client.cookies.set("echowhale_refresh_token", refresh_cookie)

    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["access_token"]
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie
    assert "echowhale_refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie


def test_resend_verification_returns_no_content(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "learner@example.com"},
    )

    assert response.status_code == 204


def test_resend_verification_returns_structured_503_when_mail_queue_publish_fails(
    client: TestClient,
) -> None:
    fake_service = FakeAuthService()
    fake_service.raise_on_resend = QueuePublishError("邮件任务入队失败，请稍后重试。")
    app.dependency_overrides[get_auth_service] = lambda: fake_service

    response = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "learner@example.com"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": 1005,
        "message": "邮件任务入队失败，请稍后重试。",
    }


def test_verify_email_returns_no_content(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "learner@example.com", "code": "123456"},
    )

    assert response.status_code == 204


def test_forgot_password_returns_no_content(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "learner@example.com"},
    )

    assert response.status_code == 204


def test_reset_password_returns_no_content(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": "reset-token",
            "password": "renew1234",
        },
    )

    assert response.status_code == 204


def test_login_rate_limit_returns_429(client: TestClient) -> None:
    limiter = _fake_rate_limiter()
    limiter.blocked_action = "login"
    app.dependency_overrides[get_auth_rate_limiter] = lambda: limiter

    response = client.post("/api/v1/auth/login", json=_login_payload())

    assert response.status_code == 429
    assert response.json()["code"] == 1006


def test_history_requires_authenticated_user(client: TestClient) -> None:
    response = client.get("/api/v1/history/sessions")

    assert response.status_code == 401
    assert response.json() == {
        "code": 1002,
        "message": "Authentication required",
    }


def test_logout_revokes_refresh_cookie(client: TestClient) -> None:
    _, refresh_cookie = _login_user(client)
    client.cookies.set("echowhale_refresh_token", refresh_cookie)

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie
    assert "echowhale_refresh_token=" in set_cookie
    assert "Max-Age=0" in set_cookie

