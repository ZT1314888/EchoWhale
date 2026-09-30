"""媒体场景分析状态端点测试：unknown/pending/ready/failed/越权/缺失。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.common.enums import MediaUploadStatus
from api.common.exceptions import NotFoundError
from api.db.scene_analysis_db import SceneAnalysisSnapshot
from api.main import app
from api.models.user_model import User
from api.models.media_model import Media
from api.routes.v1.media import get_media_repository, get_scene_analysis_store


class FakeMediaRepository:
    def __init__(self, media: Media | None) -> None:
        self._media = media

    async def get_media(self, media_id: str) -> Media:
        if self._media is None or self._media.id != media_id:
            raise NotFoundError(f"Media {media_id} not found")
        return self._media


class FakeSceneStore:
    def __init__(self, snapshot: SceneAnalysisSnapshot | None) -> None:
        self._snapshot = snapshot

    async def get(self, media_id: str):
        return self._snapshot


def _media() -> Media:
    return Media(
        id="med_1",
        user_id="user:user_123",
        filename="coffee.png",
        content_type="image/png",
        file_size=10,
        storage_key="k",
        upload_status=MediaUploadStatus.uploaded,
    )


def _snapshot(**overrides) -> SceneAnalysisSnapshot:
    base = dict(
        media_id="med_1",
        status="ready",
        prompt_version="v1",
        scene="coffee_shop",
        role="barista",
        opener="Hi!",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        confidence=0.88,
        error_code=None,
    )
    base.update(overrides)
    return SceneAnalysisSnapshot(**base)


class FakeAuthService:
    def get_current_user(self, *, access_token: str) -> User:
        if access_token != "valid-access-token":
            from api.common.exceptions import AuthenticationError

            raise AuthenticationError("Authentication required")
        return User(id="user_123", email="learner@example.com", nickname="Learner")


@pytest.fixture
def client():
    from api.routes.v1.auth import get_auth_service

    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


AUTH = {"Authorization": "Bearer valid-access-token"}


def _install(test_client: TestClient, media: Media | None, snapshot) -> None:
    app.dependency_overrides[get_media_repository] = lambda: FakeMediaRepository(media)
    app.dependency_overrides[get_scene_analysis_store] = lambda: FakeSceneStore(snapshot)


def test_scene_status_reports_ready_payload(client: TestClient) -> None:
    _install(client, _media(), _snapshot())

    response = client.get("/api/v1/media/med_1/scene-analysis", headers=AUTH)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ready"
    assert data["scene"] == "coffee_shop"
    assert data["role"] == "barista"
    assert data["confidence"] == pytest.approx(0.88)
    assert data["prompt_version"] == "v1"


def test_scene_status_reports_pending_failed_and_unknown(client: TestClient) -> None:
    _install(client, _media(), _snapshot(status="pending", scene=None))
    pending = client.get("/api/v1/media/med_1/scene-analysis", headers=AUTH).json()["data"]
    assert pending["status"] == "pending"

    _install(
        client,
        _media(),
        _snapshot(status="failed", scene=None, confidence=None, error_code=1007),
    )
    failed = client.get("/api/v1/media/med_1/scene-analysis", headers=AUTH).json()["data"]
    assert failed["status"] == "failed"
    assert failed["error_code"] == 1007

    _install(client, _media(), None)
    unknown = client.get("/api/v1/media/med_1/scene-analysis", headers=AUTH).json()["data"]
    assert unknown["status"] == "unknown"


def test_scene_status_hides_missing_and_foreign_media(client: TestClient) -> None:
    _install(client, None, None)
    assert client.get("/api/v1/media/med_x/scene-analysis", headers=AUTH).status_code == 404

    # 归属校验：他人媒体一律收敛成 404，避免探测。
    foreign = Media(
        id="med_foreign",
        user_id="user:other",
        filename="coffee.png",
        content_type="image/png",
        file_size=10,
        storage_key="k",
        upload_status=MediaUploadStatus.uploaded,
    )
    _install(client, foreign, _snapshot())
    assert client.get("/api/v1/media/med_foreign/scene-analysis", headers=AUTH).status_code == 404
