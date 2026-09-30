"""start() 场景缓存命中 / RQ 异步派发 / Redis 缺席降级的分支直测。"""

from __future__ import annotations

import asyncio

import pytest

from api.common.enums import MediaUploadStatus
from api.core.config import settings
from api.db.scene_analysis_db import SCENE_ANALYSIS_STATUS_READY
from api.models.media_model import Media
from api.modules.scene_engine.schema import SceneAnalysisResult
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.schema import SceneAnalysisPending, StartSessionInput


class FakeMediaLookup:
    def __init__(self, media: Media) -> None:
        self._media = media

    async def get_media(self, media_id: str) -> Media:
        assert media_id == self._media.id
        return self._media


class FakeReadUrlSigner:
    def __init__(self) -> None:
        self.signed_keys: list[str] = []

    async def async_create_signed_read_url(self, storage_key: str, **kwargs):
        self.signed_keys.append(storage_key)
        return (f"https://signed.test/{storage_key}", object())


class CountingSceneEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def analyze(self, filename: str, media_url: str) -> SceneAnalysisResult:
        self.calls.append((filename, media_url))
        return SceneAnalysisResult(
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            visual_anchors=["counter", "menu board"],
            vocab_candidates=["latte", "order"],
            confidence=0.9,
        )


class FakeSceneAnalysisStore:
    def __init__(self, snapshot=None) -> None:
        self._snapshot = snapshot
        self.pending: list[tuple[str, str]] = []
        self.results: list[dict[str, object]] = []
        self.failures: list[dict[str, object]] = []

    async def get(self, media_id: str):
        return self._snapshot

    async def save_pending(self, media_id: str, prompt_version: str) -> None:
        self.pending.append((media_id, prompt_version))
        self._snapshot = None  # pending 行不可再命中

    async def save_result(self, media_id: str, prompt_version: str, **payload) -> None:
        from api.db.scene_analysis_db import SceneAnalysisSnapshot

        self.results.append({"media_id": media_id, "prompt_version": prompt_version, **payload})
        self._snapshot = SceneAnalysisSnapshot(
            media_id=media_id,
            status=SCENE_ANALYSIS_STATUS_READY,
            prompt_version=prompt_version,
            scene=payload.get("scene"),
            role=payload.get("role"),
            opener=payload.get("opener"),
            visual_anchors=list(payload.get("visual_anchors") or []),
            vocab_candidates=list(payload.get("vocab_candidates") or []),
            confidence=payload.get("confidence"),
        )

    async def save_failure(self, media_id: str, prompt_version: str, *, error_code: int) -> None:
        self.failures.append({"media_id": media_id, "prompt_version": prompt_version, "error_code": error_code})


class RecordingDispatcher:
    def __init__(self, queued: bool) -> None:
        self.queued = queued
        self.dispatched: list[str] = []

    def __call__(self, media_id: str) -> bool:
        self.dispatched.append(media_id)
        return self.queued


def _media() -> Media:
    return Media(
        id="med_cached",
        user_id="demo-user",
        filename="coffee-shop.png",
        content_type="image/png",
        file_size=1024,
        storage_key="media/demo-user/coffee-shop.png",
        upload_status=MediaUploadStatus.uploaded,
    )


def _ready_snapshot(prompt_version: str):
    from api.db.scene_analysis_db import SceneAnalysisSnapshot

    return SceneAnalysisSnapshot(
        media_id="med_cached",
        status=SCENE_ANALYSIS_STATUS_READY,
        prompt_version=prompt_version,
        scene="travel",
        role="local_guide",
        opener="Where are you heading?",
        visual_anchors=["platform sign"],
        vocab_candidates=["ticket", "platform"],
        confidence=0.82,
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def mock_runtime(monkeypatch):
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    monkeypatch.setattr(settings, "scene_analysis_cache_enabled", True)
    monkeypatch.setattr(settings, "scene_analysis_async_enabled", False)
    monkeypatch.setattr(settings, "scene_analysis_prompt_version", "v1")


@pytest.mark.anyio
async def test_start_reuses_ready_cache_without_signing_or_vision(mock_runtime) -> None:
    store = FakeSceneAnalysisStore(_ready_snapshot("v1"))
    signer = FakeReadUrlSigner()
    engine = CountingSceneEngine()
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(_media()),
        session_repository=RecordingRepository(),
        read_url_signer=signer,
        scene_analysis_store=store,
        scene_dispatcher=RecordingDispatcher(True),
    )
    agent.scene_engine = engine

    session = await agent.start(StartSessionInput(user_id="demo-user", media_id="med_cached"))

    assert session.scene == "travel"
    assert session.role == "local_guide"
    assert session.opener == "Where are you heading?"
    assert session.vocab_candidates == ["ticket", "platform"]
    assert engine.calls == []
    assert signer.signed_keys == []


@pytest.mark.anyio
async def test_start_ignores_cache_with_different_prompt_version(mock_runtime) -> None:
    store = FakeSceneAnalysisStore(_ready_snapshot("v0"))
    engine = CountingSceneEngine()
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(_media()),
        session_repository=RecordingRepository(),
        read_url_signer=FakeReadUrlSigner(),
        scene_analysis_store=store,
        scene_dispatcher=RecordingDispatcher(True),
    )
    agent.scene_engine = engine

    session = await agent.start(StartSessionInput(user_id="demo-user", media_id="med_cached"))

    assert session.scene == "coffee_shop"
    assert len(engine.calls) == 1
    # 重分析结果写穿缓存，版本随之刷新。
    assert store.results and store.results[0]["prompt_version"] == "v1"


@pytest.mark.anyio
async def test_start_inline_analysis_writes_through_cache(mock_runtime) -> None:
    store = FakeSceneAnalysisStore(None)
    engine = CountingSceneEngine()
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(_media()),
        session_repository=RecordingRepository(),
        read_url_signer=FakeReadUrlSigner(),
        scene_analysis_store=store,
        scene_dispatcher=RecordingDispatcher(True),
    )
    agent.scene_engine = engine

    session = await agent.start(StartSessionInput(user_id="demo-user", media_id="med_cached"))

    assert session.scene == "coffee_shop"
    assert len(engine.calls) == 1
    assert store.results and store.results[0]["scene"] == "coffee_shop"
    assert store.results[0]["confidence"] == pytest.approx(0.9)

    # 二次 start：命中缓存，不再触发视觉调用（验收指标）。
    second = await agent.start(StartSessionInput(user_id="demo-user", media_id="med_cached"))
    assert second.scene == "coffee_shop"
    assert len(engine.calls) == 1


@pytest.mark.anyio
async def test_start_dispatches_to_queue_when_live_and_async_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "scene_analysis_cache_enabled", True)
    monkeypatch.setattr(settings, "scene_analysis_async_enabled", True)
    monkeypatch.setattr(settings, "scene_analysis_prompt_version", "v1")
    # 密闭性：live 构造要求一个"真实"槽位，但不依赖本机 .env 的真实密钥；
    # 两个用例随后都会把 scene_engine 换成 fake，真实客户端不会被调用。
    monkeypatch.setattr(settings, "vision_primary_provider", "ci-fake")
    monkeypatch.setattr(settings, "vision_primary_base_url", "https://vision.invalid/v1")
    monkeypatch.setattr(settings, "vision_primary_api_key", "ci-fake-key")
    monkeypatch.setattr(settings, "vision_primary_model", "ci-fake-model")
    monkeypatch.setattr(settings, "text_primary_provider", "ci-fake")
    monkeypatch.setattr(settings, "text_primary_base_url", "https://text.invalid/v1")
    monkeypatch.setattr(settings, "text_primary_api_key", "ci-fake-key")
    monkeypatch.setattr(settings, "text_primary_model", "ci-fake-model")

    store = FakeSceneAnalysisStore(None)
    engine = CountingSceneEngine()
    dispatcher = RecordingDispatcher(True)
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(_media()),
        session_repository=RecordingRepository(),
        read_url_signer=FakeReadUrlSigner(),
        scene_analysis_store=store,
        scene_dispatcher=dispatcher,
    )
    agent.scene_engine = engine

    result = await agent.start(StartSessionInput(user_id="demo-user", media_id="med_cached"))

    assert isinstance(result, SceneAnalysisPending)
    assert result.media_id == "med_cached"
    assert result.status == "analyzing"
    assert dispatcher.dispatched == ["med_cached"]
    assert store.pending == [("med_cached", "v1")]
    # 已入队：不付视觉成本，也不建会话。
    assert engine.calls == []


@pytest.mark.anyio
async def test_start_degrades_to_inline_when_enqueue_fails(monkeypatch) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "scene_analysis_cache_enabled", True)
    monkeypatch.setattr(settings, "scene_analysis_async_enabled", True)
    monkeypatch.setattr(settings, "scene_analysis_prompt_version", "v1")
    # 密闭性：live 构造要求一个"真实"槽位，但不依赖本机 .env 的真实密钥；
    # 两个用例随后都会把 scene_engine 换成 fake，真实客户端不会被调用。
    monkeypatch.setattr(settings, "vision_primary_provider", "ci-fake")
    monkeypatch.setattr(settings, "vision_primary_base_url", "https://vision.invalid/v1")
    monkeypatch.setattr(settings, "vision_primary_api_key", "ci-fake-key")
    monkeypatch.setattr(settings, "vision_primary_model", "ci-fake-model")
    monkeypatch.setattr(settings, "text_primary_provider", "ci-fake")
    monkeypatch.setattr(settings, "text_primary_base_url", "https://text.invalid/v1")
    monkeypatch.setattr(settings, "text_primary_api_key", "ci-fake-key")
    monkeypatch.setattr(settings, "text_primary_model", "ci-fake-model")

    store = FakeSceneAnalysisStore(None)
    engine = CountingSceneEngine()
    dispatcher = RecordingDispatcher(False)
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(_media()),
        session_repository=RecordingRepository(),
        read_url_signer=FakeReadUrlSigner(),
        scene_analysis_store=store,
        scene_dispatcher=dispatcher,
    )
    agent.scene_engine = engine

    session = await agent.start(StartSessionInput(user_id="demo-user", media_id="med_cached"))

    assert session.scene == "coffee_shop"
    assert len(engine.calls) == 1
    # 入队失败：记录失败码供状态端点追溯，随即内联成功并写穿缓存。
    assert store.failures and store.failures[0]["error_code"] == 1005
    assert store.results, "内联成功后必须写穿缓存"


@pytest.mark.anyio
async def test_start_sample_preset_skips_cache_and_dispatch(mock_runtime) -> None:
    engine = CountingSceneEngine()
    agent = SessionEngineAgent(
        media_lookup=ExplodingMediaLookup(),
        session_repository=RecordingRepository(),
        read_url_signer=FakeReadUrlSigner(),
        scene_analysis_store=FakeSceneAnalysisStore(None),
        scene_dispatcher=RecordingDispatcher(True),
    )
    agent.scene_engine = engine

    session = await agent.start(StartSessionInput(user_id="demo-user", sample_scene_id="coffee"))

    assert session.media_id is None
    assert engine.calls == []


class RecordingRepository:
    """最小会话仓储：仅记录 save_session，供缓存分支断言。"""

    def __init__(self) -> None:
        self.saved: list[object] = []

    async def save_session(self, session):
        self.saved.append(session)
        return session


class ExplodingMediaLookup:
    async def get_media(self, media_id: str) -> Media:
        raise AssertionError("样例场景入口不得读取媒体记录")
