from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.common.exceptions import NotFoundError
from api.models.media_model import Media
from api.main import app

try:
    from api.routes.v1.media import get_media_service
    from api.services.media_service import MediaService
except ImportError:  # pragma: no cover - expected during red phase
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
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload_bytes(self, *, key: str, content: bytes, content_type: str) -> None:
        self.objects[key] = content

    def create_signed_read_url(self, key: str, *, expires_in: int) -> tuple[str, datetime]:
        expires_at = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
        return (f"https://signed.test/{key}?expires_in={expires_in}", expires_at)


class FakeMediaRepository:
    def __init__(self) -> None:
        self.media: dict[str, Media] = {}

    def save_media(self, media: Media) -> Media:
        self.media[media.id] = media
        return media

    def get_media(self, media_id: str) -> Media:
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
    assert body["data"]["storage_key"].startswith("media/demo-user/")
    assert body["data"]["preview_url"].startswith("https://signed.test/media/demo-user/")
    assert body["data"]["preview_url_expires_at"] == "2026-04-02T12:00:00Z"
    assert body["data"]["upload_status"] == "uploaded"


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
    assert body["data"]["storage_key"].startswith("media/demo-user/")
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
