"""GET /learners/me/profile 路由测试：401 两态、空态 200、展示映射与载荷边界。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from api.common.exceptions import AuthenticationError
from api.main import app
from api.models.learner_profile_model import LearnerProfile
from api.models.user_model import User
from api.routes.v1.auth import get_auth_service
from api.routes.v1.learners import get_learner_profile_service
from api.services.learner_profile_service import LearnerProfileService


class FakeLearnerProfileRepository:
    """LearnerProfileRepository Protocol 的内存假仓库（fakes over mocks）。"""

    def __init__(self, profile: LearnerProfile | None = None) -> None:
        self._profiles: dict[str, LearnerProfile] = {}
        if profile is not None:
            self._profiles[profile.user_id] = profile

    async def get(self, user_id: str) -> LearnerProfile | None:
        return self._profiles.get(user_id)

    async def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        self._profiles[profile.user_id] = profile
        return profile


class FakeAuthService:
    def get_current_user(self, *, access_token: str) -> User:
        if access_token != "valid-access-token":
            raise AuthenticationError("Authentication required")
        return User(id="user_123", email="learner@example.com", nickname="Echo Learner")


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    with TestClient(app) as test_client:
        yield test_client


def _install_profile(profile: LearnerProfile | None) -> None:
    app.dependency_overrides[get_learner_profile_service] = lambda: LearnerProfileService(
        FakeLearnerProfileRepository(profile)
    )


def test_profile_requires_authentication(client: TestClient) -> None:
    _install_profile(None)

    response = client.get("/api/v1/learners/me/profile")

    assert response.status_code == 401
    assert response.json()["code"] == 1002


def test_profile_rejects_invalid_access_token(client: TestClient) -> None:
    _install_profile(None)

    response = client.get(
        "/api/v1/learners/me/profile",
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == 1002


def test_missing_profile_returns_empty_payload_instead_of_404(client: TestClient) -> None:
    """空态定案：首访用户返回 200 全空载荷，前端以 practiced_turn_count 判空态。"""
    _install_profile(None)

    response = client.get(
        "/api/v1/learners/me/profile",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"] == {
        "cefr_estimate": None,
        "error_types": [],
        "scenes": [],
        "practiced_turn_count": 0,
        "updated_at": None,
    }


def test_profile_maps_display_names_and_merges_same_copy_scenes(client: TestClient) -> None:
    """有数据：top3 中文标签、场景展示名映射、street/travel 同文案合并、gym 回退。"""
    _install_profile(
        LearnerProfile(
            user_id="user:user_123",
            cefr_estimate="B1",
            error_type_counts={"tense": 5, "grammar": 3, "article": 2, "spelling": 1},
            scene_counts={"coffee_shop": 4, "street": 3, "travel": 1, "office": 2, "gym": 2},
            practiced_turn_count=18,
            updated_at=datetime(2026, 5, 10, 8, 30, tzinfo=UTC),
        )
    )

    response = client.get(
        "/api/v1/learners/me/profile",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["cefr_estimate"] == "B1"
    # top3：spelling(1) 被截掉；label 来自服务端中文映射，前端不维护副本。
    assert body["data"]["error_types"] == [
        {"category": "tense", "label": "时态", "count": 5},
        {"category": "grammar", "label": "语法", "count": 3},
        {"category": "article", "label": "冠词", "count": 2},
    ]
    # street(3)+travel(1) 合并为同一展示场景；gym 未命中预设走 humanize 回退。
    assert body["data"]["scenes"] == [
        {"scene_title": "咖啡店柜台点单", "count": 4},
        {"scene_title": "街头问路确认路线", "count": 4},
        {"scene_title": "Gym 情景对话", "count": 2},
        {"scene_title": "办公室状态同步", "count": 2},
    ]
    assert body["data"]["practiced_turn_count"] == 18
    assert body["data"]["updated_at"] == "2026-05-10 08:30"
    # F17 不变量：响应任何路径不得出现原始 scene id（契约里也没有该字段）。
    for raw_scene_id in ("coffee_shop", "office", "street", "travel", "gym"):
        assert raw_scene_id not in response.text


def test_scene_payload_is_capped_at_twelve(client: TestClient) -> None:
    """载荷边界：15 个不同场景只出 top 12（与写侧封顶、注入面常数互不引用）。"""
    _install_profile(
        LearnerProfile(
            user_id="user:user_123",
            scene_counts={f"scene_{index:02d}": 1 for index in range(15)},
            practiced_turn_count=15,
        )
    )

    response = client.get(
        "/api/v1/learners/me/profile",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert len(body["data"]["scenes"]) == 12
    # 等计数按展示名字典序决胜：zero-padded id 映射后标题可精确预期。
    assert [item["scene_title"] for item in body["data"]["scenes"]] == [
        f"Scene {index:02d} 情景对话" for index in range(12)
    ]
    for index in range(15):
        assert f"scene_{index:02d}" not in response.text
