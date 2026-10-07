"""mock 冒烟：TestClient + 方言无关引擎走真实 HTTP 全链路。

覆盖验收口径：
- 上传后的 media 两次开课：第一次内联 mock 分析并写穿缓存，第二次命中缓存
  （质量门禁与签名调用均不重复发生，即"不再触发 vision 链路"）；
- 文字回复 JSON 端点回归；
- /reply/stream SSE：feedback → delta* → session 帧序 + 会话持久化；
- 场景分析状态端点输出 ready 载荷。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.common.enums import MediaUploadStatus
from api.common.ownership import build_visitor_owner
from api.core.config import settings
from api.core.security import sign_value
from api.db.database import create_all_tables_async, create_async_session_factory
from api.db.media_db import SqlAlchemyMediaRepository
from api.db.scene_analysis_db import SqlAlchemySceneAnalysisStore
from api.db.session_db import SqlAlchemySessionRepository
from api.main import app
from api.models.media_model import Media
from api.modules.scene_engine.service import SceneEngineService
from api.modules.session_engine.service import SessionEngineService
from api.routes.v1.media import get_media_repository, get_scene_analysis_store
from api.routes.v1.sessions import get_llm_rate_limiter, get_session_service
from api.services.llm_rate_limit import InMemoryLLMRateLimiter
from tests.support.dialect import ensure_psycopg_async_compatible_loop
from tests.support.engine import build_dialect_async_engine


class RecordingQualityGate:
    """替身质量门禁：记录调用次数，模拟"命中缓存后不再下载/筛查"。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def screen(self, payload) -> None:
        self.calls.append(payload.media_url)


class FakeReadUrlSigner:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def async_create_signed_read_url(self, storage_key: str, **kwargs):
        self.keys.append(storage_key)
        return (f"https://signed.test/{storage_key}", object())


@pytest.fixture
def smoke(tmp_path, monkeypatch):
    # 陷阱 #3：本地 .env 可能是 live，冒烟必须钉死 mock。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    monkeypatch.setattr(settings, "scene_analysis_cache_enabled", True)
    monkeypatch.setattr(settings, "scene_analysis_async_enabled", False)
    monkeypatch.setattr(settings, "scene_analysis_prompt_version", "v1")

    async def _prepare() -> tuple[object, ...]:
        # 自管引擎（不经 fixture）：asyncio.run 自管 loop；builder 内含 PG 重置。
        engine = await build_dialect_async_engine(tmp_path, "smoke")
        await create_all_tables_async(engine)
        session_factory = create_async_session_factory(engine)
        media_repository = SqlAlchemyMediaRepository(session_factory)
        session_repository = SqlAlchemySessionRepository(session_factory)
        scene_store = SqlAlchemySceneAnalysisStore(session_factory)
        await media_repository.save_media(
            Media(
                id="med_smoke",
                user_id=build_visitor_owner("visitor_smoke_owner"),
                filename="coffee-shop.png",
                content_type="image/png",
                file_size=2048,
                storage_key="media/smoke/coffee-shop.png",
                upload_status=MediaUploadStatus.uploaded,
            )
        )
        # _prepare 的循环即将随 asyncio.run 关闭，而 psycopg async 连接绑定创建它的
        # 循环；先清空池，让 TestClient 门户循环上按需建新连接（SQLite 无感）。
        await engine.dispose()
        return engine, media_repository, session_repository, scene_store

    import asyncio

    # Windows 本地 PG：psycopg async 需 Selector loop，必须在 asyncio.run 建 loop 前
    # 设置策略（CI ubuntu 是 no-op）。
    ensure_psycopg_async_compatible_loop()
    engine, media_repository, session_repository, scene_store = asyncio.run(_prepare())

    gate = RecordingQualityGate()
    signer = FakeReadUrlSigner()

    service = SessionEngineService(
        media_lookup=media_repository,
        session_repository=session_repository,
        read_url_signer=signer,
    )
    service.agent.scene_engine = SceneEngineService(quality_gate=gate)
    service.agent.scene_analysis_store = scene_store
    service.agent.scene_dispatcher = lambda media_id: False

    limiter = InMemoryLLMRateLimiter()
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter
    # 媒体状态端点也必须落在 aiosqlite 上，防止默认工厂连接真实 PG。
    app.dependency_overrides[get_media_repository] = lambda: media_repository
    app.dependency_overrides[get_scene_analysis_store] = lambda: scene_store

    with TestClient(app) as test_client:
        yield test_client, gate, signer

    app.dependency_overrides.clear()

    async def _dispose() -> None:
        await engine.dispose()

    asyncio.run(_dispose())


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    frames: list[tuple[str, dict]] = []
    for frame in text.split("\n\n"):
        if not frame.strip():
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in frame.split("\n"):
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if data_lines:
            frames.append((event_name, json.loads("\n".join(data_lines))))
    return frames


def test_mock_full_chain_with_scene_cache_and_reply_stream(smoke) -> None:
    test_client, gate, signer = smoke
    # 固定访客身份：cookie 值与 fixture 种子媒体的属主一一对应。
    # 访客 Cookie 已签名化：必须用 sign_value 生成服务端可验签的值，
    # 旧版裸 id 会被验签拒绝并重新签发新身份，种子媒体将不可见。
    test_client.cookies.set(
        settings.auth_visitor_cookie_name,
        sign_value("visitor_smoke_owner", secret=settings.auth_jwt_secret),
    )

    # 1) 首次开课：内联 mock 分析 + 写穿缓存
    first = test_client.post("/api/v1/sessions", json={"media_id": "med_smoke"})
    assert first.status_code == 200
    first_body = first.json()["data"]
    assert first_body["scene"] == "coffee_shop"
    assert first_body["messages"][0]["text"]
    assert len(gate.calls) == 1
    assert len(signer.keys) == 1
    session_id = first_body["session_id"]

    # 2) 同 media 二次开课：命中缓存，不重付下载/质检/视觉（验收指标）
    second = test_client.post("/api/v1/sessions", json={"media_id": "med_smoke"})
    assert second.status_code == 200
    assert second.json()["data"]["session_id"] != session_id
    assert len(gate.calls) == 1, "缓存命中后不得再次执行质量筛查"
    assert len(signer.keys) == 1, "缓存命中后不得重签读 URL"

    # 3) 状态端点：ready 载荷
    status_response = test_client.get("/api/v1/media/med_smoke/scene-analysis")
    assert status_response.status_code == 200
    status_data = status_response.json()["data"]
    assert status_data["status"] == "ready"
    assert status_data["scene"] == "coffee_shop"
    assert status_data["prompt_version"] == "v1"

    # 4) 文字回复 JSON 端点回归
    reply = test_client.post(
        f"/api/v1/sessions/{session_id}/reply",
        json={"learner_message": "Could I get a latte, please?"},
    )
    assert reply.status_code == 200
    reply_body = reply.json()["data"]
    assert reply_body["feedback"] is not None
    assert reply_body["session"]["messages"][-2]["text"] == "Could I get a latte, please?"

    # 5) SSE 流式端点：feedback → delta* → session
    stream = test_client.post(
        f"/api/v1/sessions/{session_id}/reply/stream",
        json={"learner_message": "And an iced one, too?"},
    )
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    frames = _parse_sse(stream.text)
    names = [name for name, _ in frames]
    assert names[0] == "feedback" and names[-1] == "session"
    assert names[1:-1] and all(name == "delta" for name in names[1:-1])
    streamed_text = "".join(payload["text"] for name, payload in frames if name == "delta")
    assert streamed_text
    final_payload = frames[-1][1]
    assert final_payload["session"]["messages"][-1]["text"] == streamed_text
    assert final_payload["feedback"]["grammar"]

    # 6) 流式轮次已原子落库：重新拉取会话可见两条新消息
    refreshed = test_client.get(f"/api/v1/sessions/{session_id}").json()["data"]
    assert refreshed["messages"][-1]["text"] == streamed_text
    assert refreshed["messages"][-1]["feedback"] is not None
