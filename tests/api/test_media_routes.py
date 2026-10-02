from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import BinaryIO

import pytest
from fastapi.testclient import TestClient

from api.common.exceptions import AuthenticationError, NotFoundError
from api.core.config import settings
from api.main import app
from api.models.media_model import Media
from api.models.user_model import User
from api.services.llm_rate_limit import (
    InMemoryLLMRateLimiter,
    LLMRateLimitRule,
    get_llm_rate_limiter,
)

try:
    from api.routes.v1.auth import get_auth_service
    from api.routes.v1.media import get_media_service
    from api.services.media_service import MediaService
except ImportError:  # pragma: no cover - expected during red phase
    get_auth_service = None
    get_media_service = None
    MediaService = None


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\x0f\x00\x01\x01\x01\x00"
    b"\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeStorageService:
    """fileobj 契约替身：记录 storage 收到的完整内容与 content_type。"""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}

    async def async_upload_fileobj(self, *, key: str, fileobj: BinaryIO, content_type: str) -> None:
        # 服务侧校验通过后已 seek(0)，这里读到的是完整文件内容。
        self.objects[key] = fileobj.read()
        self.content_types[key] = content_type

    async def async_create_signed_read_url(
        self, key: str, *, expires_in: int
    ) -> tuple[str, datetime]:
        expires_at = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
        return (f"https://signed.test/{key}?expires_in={expires_in}", expires_at)


class FakeMediaRepository:
    def __init__(self) -> None:
        self.media: dict[str, Media] = {}

    async def save_media(self, media: Media) -> Media:
        self.media[media.id] = media
        return media

    async def get_media(self, media_id: str) -> Media:
        if media_id not in self.media:
            raise NotFoundError(f"Media {media_id} not found")
        return self.media[media_id]


@pytest.fixture(autouse=True)
def clear_media_store() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_media_repository() -> FakeMediaRepository:
    return FakeMediaRepository()


@pytest.fixture
def client(fake_media_repository: FakeMediaRepository) -> Iterator[TestClient]:
    if get_media_service is not None and MediaService is not None:
        app.dependency_overrides[get_media_service] = lambda: MediaService(
            storage=FakeStorageService(),
            repository=fake_media_repository,
        )
    # 每个测试用独立限流器，与 lru_cache 的全局实例隔离，避免用例间计数串扰；
    # 注意必须绑定单例再进 lambda：在 lambda 内构造会让每次请求都拿到新实例。
    limiter = InMemoryLLMRateLimiter()
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    with TestClient(app) as test_client:
        yield test_client


def override_media_service(
    fake_media_repository: FakeMediaRepository,
    *,
    max_file_size: int = 10 * 1024 * 1024,
) -> None:
    if get_media_service is not None and MediaService is not None:
        app.dependency_overrides[get_media_service] = lambda: MediaService(
            storage=FakeStorageService(),
            repository=fake_media_repository,
            max_file_size=max_file_size,
        )
    limiter = InMemoryLLMRateLimiter()
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter


def test_upload_image_returns_media_metadata(client: TestClient) -> None:
    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("coffee-shop.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "Success"
    assert body["data"]["media_id"]
    assert body["data"]["filename"] == "coffee-shop.png"
    assert body["data"]["content_type"] == "image/png"
    assert body["data"]["file_size"] == len(PNG_BYTES)
    assert body["data"]["storage_key"].startswith("media/visitor/")
    assert body["data"]["preview_url"].startswith("https://signed.test/media/visitor/")
    assert body["data"]["preview_url_expires_at"] == "2026-04-02T12:00:00Z"
    assert body["data"]["upload_status"] == "uploaded"
    assert "echowhale_visitor_id=" in response.headers.get("set-cookie", "")


def test_upload_rejects_unsupported_content_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("notes.txt", b"not-an-image", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json() == {
        "code": 1001,
        "message": "Unsupported media type: text/plain",
    }


def test_upload_rejects_invalid_png_signature(client: TestClient) -> None:
    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("fake.png", b"not-a-real-png", "image/png")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": 1001,
        "message": "Invalid image content for image/png",
    }


def test_upload_rejects_oversized_file(
    client: TestClient,
    fake_media_repository: FakeMediaRepository,
) -> None:
    override_media_service(fake_media_repository, max_file_size=8)

    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("large.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 413
    assert response.json() == {
        "code": 1001,
        "message": "File exceeds size limit of 8 bytes",
    }


def test_get_media_returns_stored_metadata(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/media/upload",
        files={"file": ("lunch.png", PNG_BYTES, "image/png")},
    )
    media_id = upload_response.json()["data"]["media_id"]

    response = client.get(f"/api/v1/media/{media_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "Success"
    assert body["data"]["media_id"] == media_id
    assert body["data"]["filename"] == "lunch.png"
    assert body["data"]["storage_key"].startswith("media/visitor/")
    assert body["data"]["upload_status"] == "uploaded"
    assert body["data"]["preview_url"] is None
    assert body["data"]["preview_url_expires_at"] is None


def test_get_media_access_url_returns_signed_read_url(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/media/upload",
        files={"file": ("lunch.png", PNG_BYTES, "image/png")},
    )
    media_id = upload_response.json()["data"]["media_id"]

    response = client.get(f"/api/v1/media/{media_id}/access-url")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "Success"
    assert body["data"] == {
        "media_id": media_id,
        "read_url": upload_response.json()["data"]["preview_url"],
        "expires_at": "2026-04-02T12:00:00Z",
    }


def test_get_media_returns_unified_not_found_error(client: TestClient) -> None:
    response = client.get("/api/v1/media/med_missing")

    assert response.status_code == 404
    assert response.json() == {
        "code": 1004,
        "message": "Media med_missing not found",
    }


def test_upload_requires_file_with_unified_validation_error(client: TestClient) -> None:
    response = client.post("/api/v1/media/upload")

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == 1001
    assert body["message"] == "Validation error"
    assert body["data"]


def test_health_route_keeps_plain_response(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_assigns_visitor_cookie_when_request_is_anonymous(client: TestClient) -> None:
    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("coffee-shop.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 200
    set_cookie = response.headers.get("set-cookie")
    assert set_cookie
    assert "echowhale_visitor_id=" in set_cookie
    assert response.json()["data"]["storage_key"].startswith("media/visitor/")


class FakeAuthService:
    def get_current_user(self, *, access_token: str) -> User:
        if access_token != "valid-access-token":
            raise AuthenticationError("Authentication required")
        return User(id="user_123", email="learner@example.com", nickname="Echo Learner")


def override_auth_service() -> None:
    if get_auth_service is not None:
        app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()


def test_upload_returns_429_when_owner_quota_exceeded(client: TestClient) -> None:
    """owner（visitor/账号）键打满后返回 429 统一信封（code 1006）。"""
    limiter = InMemoryLLMRateLimiter(
        rules={
            "media_upload": LLMRateLimitRule(limit=1, window_seconds=3600),
            "media_upload_ip": LLMRateLimitRule(limit=100, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    # 同一 TestClient 持久化 Cookie：两次上传同一 visitor 身份，第二次撞 owner 键。
    first = client.post(
        "/api/v1/media/upload",
        files={"file": ("latte.png", PNG_BYTES, "image/png")},
    )
    second = client.post(
        "/api/v1/media/upload",
        files={"file": ("croissant.png", PNG_BYTES, "image/png")},
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == 1006


def test_anonymous_rotating_cookies_hit_ip_upload_limit(client: TestClient) -> None:
    """同 IP 轮换 Cookie 刷新上传配额：visitor 键挡不住，IP 兜底键返回 429。"""
    limiter = InMemoryLLMRateLimiter(
        rules={
            "media_upload": LLMRateLimitRule(limit=100, window_seconds=3600),
            "media_upload_ip": LLMRateLimitRule(limit=2, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    # TestClient 对端地址固定为 testclient：每次请求伪造新 Cookie 使
    # visitor 键始终全新，第 3 次请求撞上 IP 限额（limit=2）。
    responses = [
        client.post(
            "/api/v1/media/upload",
            files={"file": (f"photo-{index}.png", PNG_BYTES, "image/png")},
            headers={"Cookie": f"{settings.auth_visitor_cookie_name}=forged_{index}"},
        )
        for index in range(3)
    ]

    assert [response.status_code for response in responses[:2]] == [200, 200]
    assert responses[2].status_code == 429
    assert responses[2].json()["code"] == 1006


def test_authenticated_user_bursts_do_not_hit_upload_ip_limit(client: TestClient) -> None:
    """认证用户不受 IP 兜底键影响：IP 限额调到 1 也应连发无阻。"""
    override_auth_service()
    limiter = InMemoryLLMRateLimiter(
        rules={
            "media_upload": LLMRateLimitRule(limit=10, window_seconds=3600),
            "media_upload_ip": LLMRateLimitRule(limit=1, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    headers = {"Authorization": "Bearer valid-access-token"}
    for _ in range(3):
        response = client.post(
            "/api/v1/media/upload",
            files={"file": ("coffee-shop.png", PNG_BYTES, "image/png")},
            headers=headers,
        )
        assert response.status_code == 200
