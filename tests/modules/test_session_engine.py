from __future__ import annotations

import asyncio
import logging

import pytest

from api.common.enums import MediaUploadStatus
from api.common.exceptions import (
    EchoWhaleError,
    NotFoundError,
    SceneAnalysisUnavailableError,
    UnsupportedSceneImageError,
)
from api.common.exceptions import ValidationError as AppValidationError
from api.core.config import settings
from api.models.learner_profile_model import LearnerProfile
from api.models.media_model import Media
from api.models.message_model import Message
from api.models.runtime_model import SessionEvent, VoiceSessionFact
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackErrorItem, FeedbackResult
from api.modules.scene_engine.schema import SceneAnalysisResult
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.review_builder import (
    SCENE_COPY,
    ReviewCopy,
    get_role_label,
    get_scene_title,
)
from api.modules.session_engine.schema import (
    ReplyInput,
    StartSessionInput,
    VoiceCompleteInput,
    VoiceConversationTurn,
)
from api.modules.session_engine.service import SessionEngineService


class FakeMediaLookup:
    def __init__(self, media: Media) -> None:
        self.media = media

    async def get_media(self, media_id: str) -> Media:
        assert media_id == self.media.id
        return self.media


class ExplodingMediaLookup:
    async def get_media(self, media_id: str) -> Media:
        raise AssertionError("sample preset startup must not read media records")


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.reviews: dict[str, object] = {}
        self.events: dict[str, list[SessionEvent]] = {}
        self.voice_facts: dict[str, VoiceSessionFact] = {}
        # 记录每轮透传的 LLM 复盘文案：断言 reply/编排层把 review_copy 原样
        # 交给仓储（透传契约），None 表示 mock/降级路径。
        self.saved_review_copies: dict[str, object] = {}

    async def save_session(self, session: Session) -> Session:
        self.sessions[session.id] = session
        return session

    async def get_session(self, session_id: str) -> Session:
        return self.sessions[session_id]

    async def add_message(self, session_id: str, message: Message) -> Session:
        session = self.sessions[session_id]
        session.messages.append(message)
        self.sessions[session_id] = session
        return session

    async def save_reply_turn(
        self,
        session_id: str,
        learner_message: Message,
        assistant_message: Message,
        review,
        review_copy=None,
    ) -> Session:
        session = self.sessions[session_id]
        session.messages.extend([learner_message, assistant_message])
        self.sessions[session_id] = session
        self.reviews[session_id] = review
        self.saved_review_copies[session_id] = review_copy
        return session

    async def finalize_voice_session(
        self,
        *,
        session: Session,
        new_messages: list[Message],
        review,
        voice_fact: VoiceSessionFact,
        events: list[SessionEvent],
    ) -> tuple[Session, object]:
        # 与真实仓储的 append 语义对齐：既有消息行保持不动，只拼接新增部分。
        stored = self.sessions[session.id]
        merged = session.model_copy(update={"messages": [*stored.messages, *new_messages]})
        self.sessions[session.id] = merged
        self.reviews[review.session_id] = review
        self.voice_facts[voice_fact.session_id] = voice_fact
        self.events.setdefault(session.id, []).extend(events)
        return (merged, review)

    async def save_session_review(self, review) -> object:
        self.reviews[review.session_id] = review
        return review

    async def get_session_review(self, session_id: str):
        return self.reviews[session_id]

    async def save_session_event(self, event: SessionEvent) -> SessionEvent:
        self.events.setdefault(event.session_id, []).append(event)
        return event

    async def list_session_events(self, session_id: str) -> list[SessionEvent]:
        return list(self.events.get(session_id, []))

    async def save_voice_session_fact(self, fact: VoiceSessionFact) -> VoiceSessionFact:
        self.voice_facts[fact.session_id] = fact
        return fact

    async def get_latest_voice_session_fact(self, session_id: str) -> VoiceSessionFact | None:
        return self.voice_facts.get(session_id)

    async def get_session_head(self, session_id: str) -> Session:
        return self.sessions[session_id]

    async def list_recent_messages(self, session_id: str, *, limit: int) -> list[Message]:
        return list(self.sessions[session_id].messages[-limit:])

    async def count_session_messages(self, session_id: str) -> int:
        return len(self.sessions[session_id].messages)

    async def list_session_reviews_by_ids(self, session_ids: list[str]):
        return {
            session_id: self.reviews[session_id]
            for session_id in session_ids
            if session_id in self.reviews
        }


@pytest.fixture
def fake_session_repository() -> FakeSessionRepository:
    return FakeSessionRepository()


def test_start_session_rejects_media_that_is_not_uploaded(
    fake_session_repository: FakeSessionRepository,
) -> None:
    media = Media(
        id="med_pending",
        user_id="demo-user",
        filename="coffee-shop.png",
        content_type="image/png",
        file_size=128,
        storage_key="media/demo-user/2026/04/01/med_pending-coffee-shop.png",
        upload_status=MediaUploadStatus.pending,
    )
    service = SessionEngineService(
        media_lookup=FakeMediaLookup(media),
        session_repository=fake_session_repository,
    )

    with pytest.raises(EchoWhaleError, match="Media med_pending is not uploaded"):
        asyncio.run(service.start_session(user_id="demo-user", media_id="med_pending"))


class FakeReadUrlSigner:
    def __init__(self) -> None:
        self.requested_keys: list[str] = []

    async def async_create_signed_read_url(
        self, key: str, *, expires_in: int
    ) -> tuple[str, object]:
        self.requested_keys.append(key)
        return ("https://signed.test/media/demo-user/coffee-shop.png", object())


class FakeSceneEngine:
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
            confidence=0.83,
        )


class FailingSceneEngine:
    async def analyze(self, filename: str, media_url: str) -> SceneAnalysisResult:
        raise EchoWhaleError("vision provider unavailable")


class UnsupportedSceneEngine:
    async def analyze(self, filename: str, media_url: str) -> SceneAnalysisResult:
        raise UnsupportedSceneImageError(
            "Unsupported scene image",
            data={"reason": "image_too_uniform", "retryable": False},
        )


class ExplodingSceneEngine:
    async def analyze(self, filename: str, media_url: str) -> SceneAnalysisResult:
        raise AssertionError("sample preset startup must not call scene_engine.analyze")


def test_start_session_uses_signed_media_url_for_scene_analysis(
    fake_session_repository: FakeSessionRepository,
) -> None:
    media = Media(
        id="med_uploaded",
        user_id="demo-user",
        filename="coffee-shop.png",
        content_type="image/png",
        file_size=128,
        storage_key="media/demo-user/2026/04/01/med_uploaded-coffee-shop.png",
        upload_status=MediaUploadStatus.uploaded,
    )
    signer = FakeReadUrlSigner()
    scene_engine = FakeSceneEngine()
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(media),
        session_repository=fake_session_repository,
        read_url_signer=signer,
    )
    agent.scene_engine = scene_engine

    session = asyncio.run(agent.start(StartSessionInput(user_id="demo-user", media_id=media.id)))

    assert session.media_id == media.id
    assert session.user_id == "demo-user"
    assert signer.requested_keys == [media.storage_key]
    assert scene_engine.calls == [
        ("coffee-shop.png", "https://signed.test/media/demo-user/coffee-shop.png")
    ]


def test_start_session_propagates_scene_engine_failure_without_creating_fallback_session(
    fake_session_repository: FakeSessionRepository,
) -> None:
    media = Media(
        id="med_uploaded",
        user_id="demo-user",
        filename="mystery-upload.png",
        content_type="image/png",
        file_size=128,
        storage_key="media/demo-user/2026/04/01/med_uploaded-mystery-upload.png",
        upload_status=MediaUploadStatus.uploaded,
    )
    signer = FakeReadUrlSigner()
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(media),
        session_repository=fake_session_repository,
        read_url_signer=signer,
    )
    agent.scene_engine = FailingSceneEngine()

    with pytest.raises(SceneAnalysisUnavailableError, match="图片分析暂时不可用，请稍后重试。"):
        asyncio.run(agent.start(StartSessionInput(user_id="demo-user", media_id=media.id)))

    assert fake_session_repository.sessions == {}


def test_start_session_propagates_unsupported_scene_image_without_creating_session(
    fake_session_repository: FakeSessionRepository,
) -> None:
    media = Media(
        id="med_uploaded",
        user_id="demo-user",
        filename="black.png",
        content_type="image/png",
        file_size=128,
        storage_key="media/demo-user/2026/04/01/med_uploaded-black.png",
        upload_status=MediaUploadStatus.uploaded,
    )
    signer = FakeReadUrlSigner()
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(media),
        session_repository=fake_session_repository,
        read_url_signer=signer,
    )
    agent.scene_engine = UnsupportedSceneEngine()

    with pytest.raises(UnsupportedSceneImageError) as exc_info:
        asyncio.run(agent.start(StartSessionInput(user_id="demo-user", media_id=media.id)))

    assert exc_info.value.data == {
        "reason": "image_too_uniform",
        "retryable": False,
    }
    assert fake_session_repository.sessions == {}


class RecordingSceneAnalysisStore:
    """记录缓存全部读写的假仓储，供跨用户回归测试断言零交互。"""

    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.pending_saves: list[str] = []
        self.result_saves: list[str] = []
        self.failure_saves: list[str] = []

    async def get(self, media_id: str):
        self.get_calls.append(media_id)

    async def save_pending(self, media_id: str, prompt_version: str) -> None:
        self.pending_saves.append(media_id)

    async def save_result(self, media_id: str, prompt_version: str, **payload) -> None:
        self.result_saves.append(media_id)

    async def save_failure(self, media_id: str, prompt_version: str, *, error_code: int) -> None:
        self.failure_saves.append(media_id)


def _explode_scene_dispatch(media_id: str) -> bool:
    raise AssertionError("跨用户请求不得派发场景分析任务")


@pytest.fixture
def cache_enabled_mock_runtime(monkeypatch) -> None:
    """固定 mock 运行时并强制打开缓存开关，保证"缓存零读取"断言有拦截力。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    monkeypatch.setattr(settings, "scene_analysis_cache_enabled", True)


def test_start_session_rejects_cross_user_media_before_cache_or_analysis(
    fake_session_repository: FakeSessionRepository,
    cache_enabled_mock_runtime: None,
) -> None:
    media = Media(
        id="med_foreign",
        user_id="user:owner",
        filename="private-photo.png",
        content_type="image/png",
        file_size=128,
        storage_key="media/user-owner/2026/04/01/med_foreign-private-photo.png",
        upload_status=MediaUploadStatus.uploaded,
    )
    signer = FakeReadUrlSigner()
    store = RecordingSceneAnalysisStore()
    agent = SessionEngineAgent(
        media_lookup=FakeMediaLookup(media),
        session_repository=fake_session_repository,
        read_url_signer=signer,
        scene_analysis_store=store,
        scene_dispatcher=_explode_scene_dispatch,
    )
    agent.scene_engine = ExplodingSceneEngine()

    with pytest.raises(NotFoundError, match="Media med_foreign not found"):
        asyncio.run(agent.start(StartSessionInput(user_id="user:attacker", media_id=media.id)))

    # upload_status 已是 uploaded 仍被拒：拦截只看归属，与上传状态无关；
    # 且缓存零读取、零写入，视觉分析零派发，签名 URL 也未生成。
    assert store.get_calls == []
    assert store.pending_saves == []
    assert store.result_saves == []
    assert store.failure_saves == []
    assert signer.requested_keys == []
    assert fake_session_repository.sessions == {}


def test_start_session_from_sample_preset_bypasses_media_lookup_and_scene_engine(
    fake_session_repository: FakeSessionRepository,
) -> None:
    agent = SessionEngineAgent(
        media_lookup=ExplodingMediaLookup(),
        session_repository=fake_session_repository,
    )
    agent.scene_engine = ExplodingSceneEngine()

    session = asyncio.run(
        agent.start(StartSessionInput(user_id="demo-user", sample_scene_id="coffee"))
    )

    assert session.user_id == "demo-user"
    assert session.media_id is None
    assert session.scene == "coffee_shop"
    assert session.role
    assert session.vocab_candidates
    assert [message.text for message in session.messages] == [session.opener]
    assert asyncio.run(fake_session_repository.get_session(session.id)).scene == "coffee_shop"


class FailingCoachEngine:
    async def respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
        learner_context: str | None = None,
        learner_cefr: str | None = None,
    ):
        raise RuntimeError("coach provider unavailable")


class FakeFeedbackEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[str], str | None]] = []

    async def review(
        self,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
        learner_context: str | None = None,
    ):
        from api.modules.feedback_engine.schema import FeedbackResult

        self.calls.append((learner_message, scene, vocab_candidates, learner_context))

        return FeedbackResult(
            grammar="Your meaning is clear.",
            more_natural="Could I get an iced latte, please?",
            useful_words=vocab_candidates or ["latte", "size", "iced"],
        )


class FailingFeedbackEngine:
    async def review(
        self,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
        learner_context: str | None = None,
    ):
        raise RuntimeError("feedback provider unavailable")


class RecordingCoachEngine:
    def __init__(self) -> None:
        # 学员注入参数追加在元组尾部（下标 6/7），既有下标断言保持稳定。
        self.calls: list[
            tuple[str, str, str, list[str], list[str], list[Message], str | None, str | None]
        ] = []

    async def respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
        learner_context: str | None = None,
        learner_cefr: str | None = None,
    ):
        self.calls.append(
            (
                scene,
                role,
                learner_message,
                visual_anchors,
                vocab_candidates,
                recent_messages,
                learner_context,
                learner_cefr,
            )
        )
        from api.modules.coach_engine.schema import CoachReplyResult

        return CoachReplyResult(text=f"Let's keep practicing with {visual_anchors[0]}.")


class ConcurrentFeedbackEngine:
    def __init__(self, started: list[str], released: asyncio.Event) -> None:
        self.started = started
        self.released = released

    async def review(
        self,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
        learner_context: str | None = None,
    ):
        from api.modules.feedback_engine.schema import FeedbackResult

        self.started.append("feedback")
        await self.released.wait()
        return FeedbackResult(
            grammar="Your meaning is clear.",
            more_natural="Could I get an iced latte, please?",
            useful_words=vocab_candidates or ["latte", "size", "iced"],
        )


class ConcurrentCoachEngine:
    def __init__(self, started: list[str], released: asyncio.Event) -> None:
        self.started = started
        self.released = released

    async def respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
        learner_context: str | None = None,
        learner_cefr: str | None = None,
    ):
        from api.modules.coach_engine.schema import CoachReplyResult

        self.started.append("coach")
        await self.released.wait()
        return CoachReplyResult(text=f"Let's keep practicing with {visual_anchors[0]}.")


class FakeVoiceTokenIssuer:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def issue_token(self, ttl_seconds: int) -> tuple[str, float]:
        self.calls.append(ttl_seconds)
        return ("dg-token", float(ttl_seconds))


class FakeVoiceSettingsBuilder:
    def __init__(self) -> None:
        self.calls: list[Session] = []
        self.contexts: list[str | None] = []
        # think 代理 endpoint 由编排层按门控传入（None = 未配置代理），记录
        # 供签发接线用例断言；None 时不写键，与真实 builder 语义一致。
        self.endpoints: list[dict[str, object] | None] = []

    def build(
        self,
        session: Session,
        learner_context: str | None = None,
        think_proxy_endpoint: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.calls.append(session)
        self.contexts.append(learner_context)
        self.endpoints.append(think_proxy_endpoint)
        return {
            "type": "Settings",
            "agent": {
                "language": "en",
                "greeting": session.opener,
            },
        }


def test_reply_does_not_persist_partial_turn_when_generation_fails(
    fake_session_repository: FakeSessionRepository,
) -> None:
    session = Session(
        id="sess_123",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "order"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = FailingCoachEngine()

    with pytest.raises(RuntimeError, match="coach provider unavailable"):
        asyncio.run(
            agent.reply(
                ReplyInput(
                    session_id="sess_123", learner_message="Could I get an iced latte, please?"
                )
            )
        )

    stored = asyncio.run(fake_session_repository.get_session("sess_123"))
    assert [message.id for message in stored.messages] == ["msg_1"]


def test_reply_degrades_feedback_and_persists_when_feedback_fails(
    fake_session_repository: FakeSessionRepository,
    caplog,
) -> None:
    """反馈引擎故障只降级反馈：教练回复照常返回与落库，复盘用占位反馈构建。"""
    session = Session(
        id="sess_feedback_fail",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "menu"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FailingFeedbackEngine()
    agent.coach_engine = RecordingCoachEngine()

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        updated = asyncio.run(
            agent.reply(
                ReplyInput(session_id="sess_feedback_fail", learner_message="I would like a latte")
            )
        )

    # 教练回复完整返回，反馈为占位文案。
    assert updated.messages[-1].text == "Let's keep practicing with counter."
    assert updated.messages[-1].feedback == {
        "grammar": "本轮反馈生成失败，请继续对话；下一轮反馈会照常返回。",
        "more_natural": "（本轮没有更自然表达建议）",
        "useful_words": [],
        "errors": [],
        "cefr_level": None,
    }
    # 落库侧本轮两条消息都在，复盘也基于占位反馈正常构建。
    stored = asyncio.run(fake_session_repository.get_session("sess_feedback_fail"))
    assert [message.text for message in stored.messages[-2:]] == [
        "I would like a latte",
        "Let's keep practicing with counter.",
    ]
    review = fake_session_repository.reviews["sess_feedback_fail"]
    assert review.feedback.grammar.body == "本轮反馈生成失败，请继续对话；下一轮反馈会照常返回。"
    # 降级必须留运维痕迹：沿用 session_reply_branch_failed 事件名并带 degraded=true。
    assert "session_reply_branch_failed" in caplog.text
    assert "degraded=true" in caplog.text


class LongCoachEngine:
    """返回超长回复的教练替身：验证输出硬顶截断（Finding 11）。"""

    def __init__(self, length: int) -> None:
        self.length = length

    async def respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
        learner_context: str | None = None,
        learner_cefr: str | None = None,
    ):
        from api.modules.coach_engine.schema import CoachReplyResult

        return CoachReplyResult(text="x" * self.length)


def _save_reply_fixture_session(repository: FakeSessionRepository, session_id: str) -> None:
    """落库一个可供 reply 测试复用的最小会话。"""
    asyncio.run(
        repository.save_session(
            Session(
                id=session_id,
                user_id="demo-user",
                media_id="med_123",
                scene="coffee_shop",
                role="barista",
                opener="Hi there, what can I get started for you today?",
                visual_anchors=["counter", "menu board"],
                vocab_candidates=["latte", "menu"],
                messages=[
                    Message(
                        id="msg_1",
                        role="assistant",
                        text="Hi there, what can I get started for you today?",
                    )
                ],
            )
        )
    )


def test_reply_truncates_oversized_coach_output_with_warning(
    fake_session_repository: FakeSessionRepository, caplog, monkeypatch
) -> None:
    """教练输出硬顶（Finding 11）：3001 字符输出截断为上限长度并留 warning。"""
    # 固定 mock 模式：本测试只关心教练输出截断，复盘分支不得发起真实 LLM 调用。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_reply_fixture_session(fake_session_repository, "sess_truncate")
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = LongCoachEngine(length=settings.llm_coach_output_max_chars + 1)

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        updated = asyncio.run(
            agent.reply(
                ReplyInput(session_id="sess_truncate", learner_message="I would like a latte")
            )
        )

    assert len(updated.messages[-1].text) == settings.llm_coach_output_max_chars
    assert "coach_reply_truncated" in caplog.text
    assert "sess_truncate" in caplog.text
    assert f"length={settings.llm_coach_output_max_chars + 1}" in caplog.text
    # 落库侧同样只保留截断后的文本：超长输出不再无限撑大 Text 列。
    stored = asyncio.run(fake_session_repository.get_session("sess_truncate"))
    assert len(stored.messages[-1].text) == settings.llm_coach_output_max_chars
    assert fake_session_repository.reviews["sess_truncate"].title


def test_reply_keeps_coach_output_exactly_at_limit_without_warning(
    fake_session_repository: FakeSessionRepository, caplog, monkeypatch
) -> None:
    """边界回归：输出恰好等于上限时原样保留，不产生截断 warning。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_reply_fixture_session(fake_session_repository, "sess_boundary")
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = LongCoachEngine(length=settings.llm_coach_output_max_chars)

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        updated = asyncio.run(
            agent.reply(
                ReplyInput(session_id="sess_boundary", learner_message="I would like a latte")
            )
        )

    assert len(updated.messages[-1].text) == settings.llm_coach_output_max_chars
    assert "coach_reply_truncated" not in caplog.text


def test_reply_passes_session_labels_and_recent_messages_to_downstream_engines(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    # 固定 mock 模式：本测试只关心下游引擎入参，复盘分支不得发起真实 LLM 调用。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    session = Session(
        id="sess_labels",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "menu"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    feedback_engine = FakeFeedbackEngine()
    coach_engine = RecordingCoachEngine()
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = feedback_engine
    agent.coach_engine = coach_engine

    updated = asyncio.run(
        agent.reply(ReplyInput(session_id="sess_labels", learner_message="I would like a latte"))
    )

    assert feedback_engine.calls == [
        ("I would like a latte", "coffee_shop", ["latte", "menu"], None)
    ]
    assert coach_engine.calls[0][3] == ["counter", "menu board"]
    assert coach_engine.calls[0][4] == ["latte", "menu"]
    assert [message.text for message in coach_engine.calls[0][5]] == [
        "Hi there, what can I get started for you today?"
    ]
    assert updated.messages[-1].feedback == {
        "grammar": "Your meaning is clear.",
        "more_natural": "Could I get an iced latte, please?",
        "useful_words": ["latte", "menu"],
        "errors": [],
        "cefr_level": None,
    }


def test_reply_runs_feedback_and_coach_generation_concurrently(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    # 固定 mock 模式：本测试只关心分支并发起点，复盘分支不得发起真实 LLM 调用。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    session = Session(
        id="sess_parallel",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "menu"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))

    started: list[str] = []
    released = asyncio.Event()
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = ConcurrentFeedbackEngine(started, released)
    agent.coach_engine = ConcurrentCoachEngine(started, released)

    async def run_reply() -> Session:
        task = asyncio.create_task(
            agent.reply(
                ReplyInput(session_id="sess_parallel", learner_message="I would like a latte")
            )
        )
        for _ in range(10):
            await asyncio.sleep(0)
            if len(started) == 2:
                break
        assert started == ["feedback", "coach"]
        released.set()
        return await task

    updated = asyncio.run(run_reply())

    assert updated.messages[-1].text == "Let's keep practicing with counter."


def test_bootstrap_voice_session_returns_deepgram_token_and_settings(
    fake_session_repository: FakeSessionRepository,
) -> None:
    session = Session(
        id="sess_voice",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "menu"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    token_issuer = FakeVoiceTokenIssuer()
    settings_builder = FakeVoiceSettingsBuilder()
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.voice_token_issuer = token_issuer
    agent.voice_settings_builder = settings_builder

    bootstrap = asyncio.run(agent.bootstrap_voice_session("sess_voice"))

    assert bootstrap.session_id == "sess_voice"
    assert bootstrap.deepgram_access_token == "dg-token"
    assert bootstrap.expires_in > 0
    assert bootstrap.agent_settings["type"] == "Settings"
    assert bootstrap.session.messages[0].text == "Hi there, what can I get started for you today?"
    assert token_issuer.calls
    assert settings_builder.calls == [session]
    saved_events = asyncio.run(fake_session_repository.list_session_events("sess_voice"))
    assert [event.event_type for event in saved_events] == ["voice_bootstrapped"]
    assert saved_events[0].stage == "voice_active"
    assert saved_events[0].payload == {
        "expires_in": float(token_issuer.calls[0]),
        "output_sample_rate": 24000,
    }
    saved_voice_fact = asyncio.run(
        fake_session_repository.get_latest_voice_session_fact("sess_voice")
    )
    assert saved_voice_fact is not None
    assert saved_voice_fact.status == "active"
    assert saved_voice_fact.termination_reason is None
    assert saved_voice_fact.transcript_turn_count == 1


def test_complete_voice_session_persists_transcript_and_generates_review(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    # 固定 mock 模式：本测试只关心语音收口落库语义，复盘分支不得发起真实 LLM 调用。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    session = Session(
        id="sess_voice_complete",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "menu"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            ),
            Message(
                id="msg_existing_1",
                role="user",
                text="Can you recommend something warm?",
            ),
            Message(
                id="msg_existing_2",
                role="assistant",
                text="Sure. Our hot latte is popular today.",
            ),
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    asyncio.run(
        fake_session_repository.save_voice_session_fact(
            VoiceSessionFact(
                session_id="sess_voice_complete",
                status="active",
                transcript_turn_count=3,
            )
        )
    )

    completed = asyncio.run(
        agent.complete_voice_session(
            VoiceCompleteInput(
                session_id="sess_voice_complete",
                conversation=[
                    VoiceConversationTurn(
                        role="assistant", content="Hi there, what can I get started for you today?"
                    ),
                    VoiceConversationTurn(
                        role="user", content="Could I get an iced latte, please?"
                    ),
                    VoiceConversationTurn(
                        role="assistant", content="Of course. What size would you like?"
                    ),
                ],
                termination_reason="user_ended",
                client_diagnostics={
                    "processor_buffer_size": 2048,
                    "track_sample_rate": 48000,
                    "playback_gap_resets": 1,
                },
            )
        )
    )

    assert [message.role for message in completed.session.messages] == [
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [message.text for message in completed.session.messages] == [
        "Hi there, what can I get started for you today?",
        "Can you recommend something warm?",
        "Sure. Our hot latte is popular today.",
        "Could I get an iced latte, please?",
        "Of course. What size would you like?",
    ]
    assert completed.review.session_id == "sess_voice_complete"
    assert (
        fake_session_repository.reviews["sess_voice_complete"].feedback.grammar.body
        == "Your meaning is clear."
    )
    saved_events = asyncio.run(fake_session_repository.list_session_events("sess_voice_complete"))
    assert [event.event_type for event in saved_events] == ["voice_finalized", "review_built"]
    assert saved_events[0].payload == {
        "termination_reason": "user_ended",
        "conversation_turn_count": 3,
        "client_diagnostics": {
            "processor_buffer_size": 2048,
            "track_sample_rate": 48000,
            "playback_gap_resets": 1,
        },
    }
    saved_voice_fact = asyncio.run(
        fake_session_repository.get_latest_voice_session_fact("sess_voice_complete")
    )
    assert saved_voice_fact is not None
    assert saved_voice_fact.status == "completed"
    assert saved_voice_fact.termination_reason == "user_ended"
    assert saved_voice_fact.transcript_turn_count == 3
    assert saved_voice_fact.client_diagnostics == {
        "processor_buffer_size": 2048,
        "track_sample_rate": 48000,
        "playback_gap_resets": 1,
    }


def test_complete_voice_session_degrades_feedback_and_persists_when_feedback_fails(
    fake_session_repository: FakeSessionRepository,
    caplog,
) -> None:
    """语音收口与 reply 同款 failure policy：反馈失败降级占位反馈，收口照常落库。"""
    session = Session(
        id="sess_voice_feedback_fail",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "menu"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FailingFeedbackEngine()

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        completed = asyncio.run(
            agent.complete_voice_session(
                VoiceCompleteInput(
                    session_id="sess_voice_feedback_fail",
                    conversation=[
                        VoiceConversationTurn(
                            role="assistant",
                            content="Hi there, what can I get started for you today?",
                        ),
                        VoiceConversationTurn(
                            role="user", content="Could I get an iced latte, please?"
                        ),
                    ],
                    termination_reason="user_ended",
                )
            )
        )

    # 收口正常返回：追加消息在返回值里（语音转写以学习者发言收尾，反馈只进复盘）。
    assert [message.text for message in completed.session.messages] == [
        "Hi there, what can I get started for you today?",
        "Could I get an iced latte, please?",
    ]
    # 复盘基于占位反馈照常构建与落库。
    review = fake_session_repository.reviews["sess_voice_feedback_fail"]
    assert review.feedback.grammar.body == "本轮反馈生成失败，请继续对话；下一轮反馈会照常返回。"
    saved_events = asyncio.run(
        fake_session_repository.list_session_events("sess_voice_feedback_fail")
    )
    assert [event.event_type for event in saved_events] == ["voice_finalized", "review_built"]
    saved_voice_fact = asyncio.run(
        fake_session_repository.get_latest_voice_session_fact("sess_voice_feedback_fail")
    )
    assert saved_voice_fact is not None
    assert saved_voice_fact.status == "completed"
    assert saved_voice_fact.termination_reason == "user_ended"
    assert saved_voice_fact.transcript_turn_count == 2
    # 降级必须留运维痕迹：沿用 session_reply_branch_failed 事件名并带 degraded=true。
    assert "session_reply_branch_failed" in caplog.text
    assert "degraded=true" in caplog.text


def test_complete_voice_session_rejects_empty_conversation_with_validation_error(
    fake_session_repository: FakeSessionRepository,
) -> None:
    session = Session(
        id="sess_voice_empty",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[],
    )
    asyncio.run(fake_session_repository.save_session(session))
    service = SessionEngineService(session_repository=fake_session_repository)

    with pytest.raises(AppValidationError, match="Validation error"):
        asyncio.run(
            service.complete_voice_session(
                session_id="sess_voice_empty",
                conversation=[],
                termination_reason="user_ended",
                owner_id="demo-user",
            )
        )


def test_complete_voice_session_rejects_conversation_without_user_turn(
    fake_session_repository: FakeSessionRepository,
) -> None:
    session = Session(
        id="sess_voice_no_user",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[],
    )
    asyncio.run(fake_session_repository.save_session(session))
    service = SessionEngineService(session_repository=fake_session_repository)

    with pytest.raises(AppValidationError, match="Validation error"):
        asyncio.run(
            service.complete_voice_session(
                session_id="sess_voice_no_user",
                conversation=[
                    VoiceConversationTurn(
                        role="assistant",
                        content="Hi there, what can I get started for you today?",
                    )
                ],
                termination_reason="user_ended",
                owner_id="demo-user",
            )
        )


def test_get_session_rejects_owner_mismatch(
    fake_session_repository: FakeSessionRepository,
) -> None:
    session = Session(
        id="sess_owned",
        user_id="user:user_123",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["coffee"],
        messages=[],
    )
    asyncio.run(fake_session_repository.save_session(session))
    service = SessionEngineService(session_repository=fake_session_repository)

    with pytest.raises(NotFoundError, match="Session sess_owned not found"):
        asyncio.run(service.get_session("sess_owned", owner_id="user:user_999"))


def test_get_history_detail_rejects_owner_mismatch(
    fake_session_repository: FakeSessionRepository,
) -> None:
    session = Session(
        id="sess_history",
        user_id="user:user_123",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["coffee"],
        messages=[],
    )
    asyncio.run(fake_session_repository.save_session(session))
    fake_session_repository.reviews["sess_history"] = object()
    service = SessionEngineService(session_repository=fake_session_repository)

    with pytest.raises(NotFoundError, match="Session sess_history not found"):
        asyncio.run(service.get_history_session_detail("user:user_999", "sess_history"))


def test_get_history_session_overview_returns_real_objects(
    fake_session_repository: FakeSessionRepository,
) -> None:
    session = Session(
        id="sess_overview",
        user_id="user:user_123",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["coffee"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    review = object()
    fake_session_repository.reviews["sess_overview"] = review
    service = SessionEngineService(session_repository=fake_session_repository)

    loaded_session, loaded_review, total_messages = asyncio.run(
        service.get_history_session_overview("user:user_123", "sess_overview")
    )

    assert loaded_session.id == "sess_overview"
    assert loaded_review is review
    assert total_messages == 1


class FakeReviewSummarizer:
    """返回固定 ReviewCopy 的替身，记录调用入参；异常时原样上抛。"""

    def __init__(self, copy: ReviewCopy | Exception) -> None:
        self._copy = copy
        self.calls: list[dict[str, str]] = []

    async def summarize(
        self,
        *,
        scene: str,
        role: str,
        learner_message: str,
        feedback,
    ) -> ReviewCopy:
        self.calls.append(
            {
                "scene": scene,
                "role": role,
                "learner_message": learner_message,
            }
        )
        if isinstance(self._copy, Exception):
            raise self._copy
        return self._copy


def test_reply_mock_mode_builds_template_review_without_llm_review_call(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """mock 模式复盘仍走模板：highlight 以模板文案开头，next_try 来自场景预设。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_reply_fixture_session(fake_session_repository, "sess_mock_review")
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = RecordingCoachEngine()

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_mock_review", learner_message="I would like a latte")
        )
    )

    review = fake_session_repository.reviews["sess_mock_review"]
    assert review.highlight.startswith("你已经围绕“咖啡店柜台点单”把主要意思表达出来了。")
    assert review.next_try == SCENE_COPY["coffee_shop"]["next_try"]
    assert review.feedback.next_step.body == "下一轮试着在一句主回应后再补一句细节。"


def _pin_live_fake_provider_slots(monkeypatch) -> None:
    """密闭性：live 构造要求至少一个“真实”槽位，但不依赖本机 .env 的真实密钥。

    与 test_scene_cache 的既有惯例一致：构造期 SceneEngine/CoachEngine 会急切
    解析 vision/text 槽位（CI 无密钥即抛 ConfigurationError）；本组用例随后都
    会把 LLM 引擎换成 fake，真实客户端不会被调用。P1 若给 SessionEngineAgent
    构造新增急切解析的引擎，同样在此补槽位即可。
    """
    monkeypatch.setattr(settings, "vision_primary_provider", "ci-fake")
    monkeypatch.setattr(settings, "vision_primary_base_url", "https://vision.invalid/v1")
    monkeypatch.setattr(settings, "vision_primary_api_key", "ci-fake-key")
    monkeypatch.setattr(settings, "vision_primary_model", "ci-fake-model")
    monkeypatch.setattr(settings, "text_primary_provider", "ci-fake")
    monkeypatch.setattr(settings, "text_primary_base_url", "https://text.invalid/v1")
    monkeypatch.setattr(settings, "text_primary_api_key", "ci-fake-key")
    monkeypatch.setattr(settings, "text_primary_model", "ci-fake-model")


def test_reply_live_mode_consumes_llm_review_copy(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """live 模式复盘由 summarizer 文案替换模板字段，且消费侧对超长文案截断硬顶。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    _save_reply_fixture_session(fake_session_repository, "sess_live_review")
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = RecordingCoachEngine()
    summarizer = FakeReviewSummarizer(
        ReviewCopy(
            scene_title="Gym 情景对话",
            role_label="教练对话",
            highlight="好" * 130,
            next_try="试" * 90,
            next_step="步" * 100,
        )
    )
    agent.review_summarizer = summarizer

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_live_review", learner_message="I would like a latte")
        )
    )

    review = fake_session_repository.reviews["sess_live_review"]
    # LLM 文案替换模板字段；提示词是软约束，_bound 截断才是硬顶。
    assert len(review.highlight) == 120
    assert len(review.next_try) == 80
    assert len(review.feedback.next_step.body) == 80
    assert summarizer.calls == [
        {
            "scene": "coffee_shop",
            "role": "barista",
            "learner_message": "I would like a latte",
        }
    ]


def test_reply_live_mode_degrades_to_template_review_when_summarizer_fails(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
    caplog,
) -> None:
    """复盘是增强分支：summarizer 失败只降级模板复盘，本轮照常成功落库。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    _save_reply_fixture_session(fake_session_repository, "sess_review_fail")
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = RecordingCoachEngine()
    agent.review_summarizer = FakeReviewSummarizer(RuntimeError("review provider down"))

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        updated = asyncio.run(
            agent.reply(
                ReplyInput(session_id="sess_review_fail", learner_message="I would like a latte")
            )
        )

    review = fake_session_repository.reviews["sess_review_fail"]
    assert review.highlight.startswith("你已经围绕“咖啡店柜台点单”")
    assert review.next_try == SCENE_COPY["coffee_shop"]["next_try"]
    assert updated.messages[-1].text == "Let's keep practicing with counter."
    # 降级必须留运维痕迹：复盘专用 degraded 事件名，与反馈降级日志可区分。
    assert "session_review_copy_failed" in caplog.text
    assert "degraded=true" in caplog.text


def test_reply_live_mode_skips_review_summarizer_when_feedback_degraded(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """feedback 已降级时对占位文案做汇总没有意义：summarizer 不得被调用。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    _save_reply_fixture_session(fake_session_repository, "sess_review_skip")
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FailingFeedbackEngine()
    agent.coach_engine = RecordingCoachEngine()
    summarizer = FakeReviewSummarizer(
        ReviewCopy(
            scene_title="Gym 情景对话",
            role_label="教练对话",
            highlight="这轮你把主需求说完整了。",
            next_try="下一轮补一句细节。",
            next_step="把新学的词带进下一轮回答。",
        )
    )
    agent.review_summarizer = summarizer

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_review_skip", learner_message="I would like a latte")
        )
    )

    assert summarizer.calls == []
    review = fake_session_repository.reviews["sess_review_skip"]
    assert review.highlight.startswith("你已经围绕“咖啡店柜台点单”")


def test_complete_voice_session_live_mode_consumes_llm_review_copy(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """语音收口同样消费 LLM 复盘文案（feedback 总是成功产出，degraded=False）。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    session = Session(
        id="sess_voice_live_review",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "menu"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    summarizer = FakeReviewSummarizer(
        ReviewCopy(
            scene_title="咖啡店柜台点单",
            role_label="店员对话",
            highlight="这轮你把点单需求说完整了。",
            next_try="下一轮补一句杯型或口味细节。",
            next_step="把 useful_words 里的词带进下一轮回答。",
        )
    )
    agent.review_summarizer = summarizer

    completed = asyncio.run(
        agent.complete_voice_session(
            VoiceCompleteInput(
                session_id="sess_voice_live_review",
                conversation=[
                    VoiceConversationTurn(
                        role="assistant", content="Hi there, what can I get started for you today?"
                    ),
                    VoiceConversationTurn(
                        role="user", content="Could I get an iced latte, please?"
                    ),
                ],
                termination_reason="user_ended",
            )
        )
    )

    assert completed.review.highlight == "这轮你把点单需求说完整了。"
    assert completed.review.next_try == "下一轮补一句杯型或口味细节。"
    assert completed.review.feedback.next_step.body == "把 useful_words 里的词带进下一轮回答。"
    assert summarizer.calls[0]["learner_message"] == "Could I get an iced latte, please?"


def test_reply_mock_mode_passes_no_review_copy_to_repository(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """mock 模式 reply 透传给仓储的 review_copy 是 None：落库行为与现状一致。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_reply_fixture_session(fake_session_repository, "sess_mock_copy_none")
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = RecordingCoachEngine()

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_mock_copy_none", learner_message="I would like a latte")
        )
    )

    assert fake_session_repository.saved_review_copies["sess_mock_copy_none"] is None


def test_reply_passes_review_copy_to_repository(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """live 模式 reply 把 LLM 复盘文案原样透传仓储（展示名落库的前提）。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    _save_reply_fixture_session(fake_session_repository, "sess_copy_passthrough")
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = RecordingCoachEngine()
    copy = ReviewCopy(
        scene_title="咖啡馆柜台点单",
        role_label="店员服务",
        highlight="这轮你把点单需求说完整了。",
        next_try="下一轮补一句杯型或口味细节。",
        next_step="把 useful_words 里的词带进下一轮回答。",
    )
    agent.review_summarizer = FakeReviewSummarizer(copy)

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_copy_passthrough", learner_message="I would like a latte")
        )
    )

    assert fake_session_repository.saved_review_copies["sess_copy_passthrough"] is copy


def test_complete_voice_session_persists_llm_display_names(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """语音收口把 LLM 展示名并入收口快照：响应与落库快照都带两字段。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    session = Session(
        id="sess_voice_llm_names",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.review_summarizer = FakeReviewSummarizer(
        ReviewCopy(
            scene_title="咖啡店柜台点单",
            role_label="店员服务",
            highlight="这轮你把点单需求说完整了。",
            next_try="下一轮补一句杯型或口味细节。",
            next_step="把 useful_words 里的词带进下一轮回答。",
        )
    )

    completed = asyncio.run(
        agent.complete_voice_session(
            VoiceCompleteInput(
                session_id="sess_voice_llm_names",
                conversation=[
                    VoiceConversationTurn(
                        role="assistant", content="Hi there, what can I get started for you today?"
                    ),
                    VoiceConversationTurn(
                        role="user", content="Could I get an iced latte, please?"
                    ),
                ],
                termination_reason="user_ended",
            )
        )
    )

    assert completed.session.llm_scene_title == "咖啡店柜台点单"
    assert completed.session.llm_role_label == "店员服务"
    stored = fake_session_repository.sessions["sess_voice_llm_names"]
    assert stored.llm_scene_title == "咖啡店柜台点单"
    assert stored.llm_role_label == "店员服务"


def test_complete_voice_session_mock_mode_keeps_existing_display_names(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """mock 模式语音收口不触碰展示名：沿用读取时的既有值（不回闪）。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    session = Session(
        id="sess_voice_llm_keep",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        llm_scene_title="咖啡店柜台点单",
        llm_role_label="店员服务",
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    asyncio.run(fake_session_repository.save_session(session))
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()

    completed = asyncio.run(
        agent.complete_voice_session(
            VoiceCompleteInput(
                session_id="sess_voice_llm_keep",
                conversation=[
                    VoiceConversationTurn(
                        role="assistant", content="Hi there, what can I get started for you today?"
                    ),
                    VoiceConversationTurn(
                        role="user", content="Could I get an iced latte, please?"
                    ),
                ],
                termination_reason="user_ended",
            )
        )
    )

    assert completed.session.llm_scene_title == "咖啡店柜台点单"
    assert completed.session.llm_role_label == "店员服务"


def test_unknown_scene_labels_use_natural_language_fallback() -> None:
    """未知场景（如视觉模型返回 gym）不得把原始 scene id 当标题/角色标签。"""
    title = get_scene_title("gym")
    assert title != "gym"
    assert "情景对话" in title
    assert title.startswith("Gym")

    titled = get_scene_title("gym", "fitness_trainer")
    assert titled == "Gym · Fitness Trainer 情景对话"

    role_label = get_role_label("gym", "fitness_trainer")
    assert role_label == "角色 · Fitness Trainer"

    # 已知场景预设文案不受回退改造影响（history 契约共用这两个函数）。
    assert get_scene_title("coffee_shop") == "咖啡店柜台点单"
    assert get_role_label("coffee_shop", "barista") == "店员对话"


class FakeLearnerProfileRepository:
    """实现 LearnerProfileRepository 协议的内存替身，记录全部读写。"""

    def __init__(self, *, fail_on_get: bool = False, fail_on_upsert: bool = False) -> None:
        self.profiles: dict[str, LearnerProfile] = {}
        self.get_calls: list[str] = []
        self.upsert_calls: list[str] = []
        self._fail_on_get = fail_on_get
        self._fail_on_upsert = fail_on_upsert

    async def get(self, user_id: str) -> LearnerProfile | None:
        self.get_calls.append(user_id)
        if self._fail_on_get:
            raise RuntimeError("profile store read failed")
        return self.profiles.get(user_id)

    async def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        if self._fail_on_upsert:
            raise RuntimeError("profile store unavailable")
        self.upsert_calls.append(profile.user_id)
        self.profiles[profile.user_id] = profile
        return profile


class StructuredFeedbackEngine:
    """返回带 errors / cefr_level 的反馈替身：验证档案累积的信号来源。"""

    def __init__(self, *, categories: list[str], cefr_level: str | None = None) -> None:
        self._categories = categories
        self._cefr_level = cefr_level
        self.calls: list[dict[str, object]] = []

    async def review(
        self,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
        learner_context: str | None = None,
    ):
        self.calls.append(
            {
                "learner_message": learner_message,
                "scene": scene,
                "learner_context": learner_context,
            }
        )
        return FeedbackResult(
            grammar="Watch the past tense.",
            more_natural="Yesterday I went to the coffee shop.",
            useful_words=vocab_candidates or ["latte"],
            errors=[
                FeedbackErrorItem(
                    category=category,
                    original="I go",
                    correction="I went",
                    explanation="Use the past tense.",
                )
                for category in self._categories
            ],
            cefr_level=self._cefr_level,
        )


def _save_profile_fixture_session(
    repository: FakeSessionRepository, session_id: str, *, user_id: str
) -> None:
    """落库一个可供档案链路测试复用的最小会话（user_id 由用例指定）。"""
    asyncio.run(
        repository.save_session(
            Session(
                id=session_id,
                user_id=user_id,
                media_id="med_123",
                scene="coffee_shop",
                role="barista",
                opener="Hi there, what can I get started for you today?",
                visual_anchors=["counter"],
                vocab_candidates=["latte"],
                messages=[
                    Message(
                        id="msg_1",
                        role="assistant",
                        text="Hi there, what can I get started for you today?",
                    )
                ],
            )
        )
    )


def _profile_agent(
    fake_session_repository: FakeSessionRepository,
    profile_repository: FakeLearnerProfileRepository,
) -> SessionEngineAgent:
    agent = SessionEngineAgent(
        session_repository=fake_session_repository,
        learner_profile_repository=profile_repository,
    )
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = RecordingCoachEngine()
    return agent


def test_reply_persists_learner_profile_for_authenticated_user(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """认证用户 reply 落库后档案正确累积：错误计数 / 场景 / 轮数 / CEFR 估计。"""
    # 固定 mock 模式：本地 .env 是 live 模式，不 pin 会打真 LLM。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_profile_fixture_session(fake_session_repository, "sess_profile_user", user_id="user:42")
    feedback_engine = StructuredFeedbackEngine(categories=["tense", "tense"], cefr_level="B1")
    profile_repository = FakeLearnerProfileRepository()
    agent = SessionEngineAgent(
        session_repository=fake_session_repository,
        learner_profile_repository=profile_repository,
    )
    agent.feedback_engine = feedback_engine
    agent.coach_engine = RecordingCoachEngine()

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_profile_user", learner_message="I would like a latte")
        )
    )

    profile = profile_repository.profiles["user:42"]
    assert profile.error_type_counts == {"tense": 2}
    assert profile.scene_counts == {"coffee_shop": 1}
    assert profile.practiced_turn_count == 1
    assert profile.cefr_history == ["B1"]
    assert profile.cefr_estimate == "B1"


def test_reply_skips_learner_profile_for_visitor_owner(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """visitor 会话不入档：零点查、零写入（键无界且无清理语义，显式排除）。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_profile_fixture_session(
        fake_session_repository, "sess_profile_visitor", user_id="visitor:abc123"
    )
    profile_repository = FakeLearnerProfileRepository()
    agent = _profile_agent(fake_session_repository, profile_repository)

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_profile_visitor", learner_message="I would like a latte")
        )
    )

    assert profile_repository.get_calls == []
    assert profile_repository.upsert_calls == []
    assert profile_repository.profiles == {}


def test_reply_carries_learner_context_into_coach_and_feedback_payloads(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """有档案时注入块（CEFR + top 错误类别 + 轮数）同时喂给教练与反馈分支。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_profile_fixture_session(fake_session_repository, "sess_profile_inject", user_id="user:42")
    profile_repository = FakeLearnerProfileRepository()
    profile_repository.profiles["user:42"] = LearnerProfile(
        user_id="user:42",
        cefr_estimate="B1",
        error_type_counts={"tense": 2, "article": 4},
        practiced_turn_count=6,
    )
    feedback_engine = FakeFeedbackEngine()
    coach_engine = RecordingCoachEngine()
    agent = SessionEngineAgent(
        session_repository=fake_session_repository,
        learner_profile_repository=profile_repository,
    )
    agent.feedback_engine = feedback_engine
    agent.coach_engine = coach_engine

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_profile_inject", learner_message="I would like a latte")
        )
    )

    expected_context = (
        "Learner profile: estimated CEFR B1.\n"
        "Learner profile: frequent error categories so far: article, tense.\n"
        "Learner profile: 6 practice turns completed."
    )
    assert coach_engine.calls[0][6] == expected_context
    assert coach_engine.calls[0][7] == "B1"
    assert feedback_engine.calls[0][3] == expected_context


def test_reply_degrades_to_static_injection_when_profile_read_fails(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
    caplog,
) -> None:
    """档案读失败是增强分支故障：本轮照常成功，注入回退静态且留 degraded 日志。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_profile_fixture_session(
        fake_session_repository, "sess_profile_readfail", user_id="user:42"
    )
    profile_repository = FakeLearnerProfileRepository(fail_on_get=True)
    agent = _profile_agent(fake_session_repository, profile_repository)

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        updated = asyncio.run(
            agent.reply(
                ReplyInput(
                    session_id="sess_profile_readfail", learner_message="I would like a latte"
                )
            )
        )

    assert updated.messages[-1].text == "Let's keep practicing with counter."
    # 教练 payload 未携带任何注入块（回退静态水平行）。
    assert agent.coach_engine.calls[0][6] is None
    assert agent.coach_engine.calls[0][7] is None
    assert "learner_profile_load_failed" in caplog.text
    assert "degraded=true" in caplog.text


def test_reply_succeeds_and_logs_degraded_when_profile_upsert_fails(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
    caplog,
) -> None:
    """档案写失败绝不影响回复轮：本轮照常落库返回，warning 带 degraded=true。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_profile_fixture_session(
        fake_session_repository, "sess_profile_writefail", user_id="user:42"
    )
    profile_repository = FakeLearnerProfileRepository(fail_on_upsert=True)
    agent = _profile_agent(fake_session_repository, profile_repository)

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        updated = asyncio.run(
            agent.reply(
                ReplyInput(
                    session_id="sess_profile_writefail", learner_message="I would like a latte"
                )
            )
        )

    assert updated.messages[-1].text == "Let's keep practicing with counter."
    assert [message.text for message in updated.messages[-2:]] == [
        "I would like a latte",
        "Let's keep practicing with counter.",
    ]
    assert "learner_profile_update_failed" in caplog.text
    assert "degraded=true" in caplog.text
    assert "user_id=user:42" in caplog.text


def test_reply_mock_feedback_keeps_estimate_untouched_but_grows_turn_and_scene(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """mock 反馈 cefr_level=None：estimate/history 不动，场景与轮数照常累计。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_profile_fixture_session(fake_session_repository, "sess_profile_mock", user_id="user:42")
    profile_repository = FakeLearnerProfileRepository()
    profile_repository.profiles["user:42"] = LearnerProfile(
        user_id="user:42",
        cefr_estimate="B2",
        cefr_history=["A2", "B1", "B2"],
        practiced_turn_count=3,
    )
    agent = _profile_agent(fake_session_repository, profile_repository)

    asyncio.run(
        agent.reply(
            ReplyInput(session_id="sess_profile_mock", learner_message="I would like a latte")
        )
    )

    profile = profile_repository.profiles["user:42"]
    assert profile.cefr_estimate == "B2"
    assert profile.cefr_history == ["A2", "B1", "B2"]
    assert profile.practiced_turn_count == 4
    assert profile.scene_counts == {"coffee_shop": 1}


def test_bootstrap_voice_session_injects_learner_context_into_settings_builder(
    fake_session_repository: FakeSessionRepository,
) -> None:
    """语音 bootstrap 点查档案并把注入块传进 settings builder（think prompt 来源）。"""
    _save_profile_fixture_session(fake_session_repository, "sess_voice_profile", user_id="user:42")
    profile_repository = FakeLearnerProfileRepository()
    profile_repository.profiles["user:42"] = LearnerProfile(
        user_id="user:42",
        cefr_estimate="B1",
        error_type_counts={"tense": 3},
        practiced_turn_count=5,
    )
    token_issuer = FakeVoiceTokenIssuer()
    settings_builder = FakeVoiceSettingsBuilder()
    agent = SessionEngineAgent(
        session_repository=fake_session_repository,
        learner_profile_repository=profile_repository,
    )
    agent.voice_token_issuer = token_issuer
    agent.voice_settings_builder = settings_builder

    asyncio.run(agent.bootstrap_voice_session("sess_voice_profile"))

    assert settings_builder.contexts == [
        (
            "Learner profile: estimated CEFR B1.\n"
            "Learner profile: frequent error categories so far: tense.\n"
            "Learner profile: 5 practice turns completed."
        )
    ]


def test_complete_voice_session_persists_learner_profile(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """语音收口成功后档案更新：最后一轮学习者发言的反馈信号入档。"""
    # 固定 mock 模式：复盘分支不得发起真实 LLM 调用。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_profile_fixture_session(
        fake_session_repository, "sess_voice_complete_profile", user_id="user:42"
    )
    feedback_engine = StructuredFeedbackEngine(categories=["word_choice"], cefr_level="B2")
    profile_repository = FakeLearnerProfileRepository()
    agent = SessionEngineAgent(
        session_repository=fake_session_repository,
        learner_profile_repository=profile_repository,
    )
    agent.feedback_engine = feedback_engine
    asyncio.run(
        fake_session_repository.save_voice_session_fact(
            VoiceSessionFact(
                session_id="sess_voice_complete_profile",
                status="active",
                transcript_turn_count=1,
            )
        )
    )

    asyncio.run(
        agent.complete_voice_session(
            VoiceCompleteInput(
                session_id="sess_voice_complete_profile",
                conversation=[
                    VoiceConversationTurn(
                        role="assistant", content="Hi there, what can I get started for you today?"
                    ),
                    VoiceConversationTurn(
                        role="user", content="Could I get an iced latte, please?"
                    ),
                ],
                termination_reason="user_ended",
            )
        )
    )

    profile = profile_repository.profiles["user:42"]
    assert profile.error_type_counts == {"word_choice": 1}
    assert profile.scene_counts == {"coffee_shop": 1}
    assert profile.practiced_turn_count == 1
    assert profile.cefr_estimate == "B2"


class FakeThinkTokenIssuer:
    """think 代理令牌签发替身：确定性令牌串，记录 (sid, generation) 调用。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def issue(self, session_id: str, *, generation: int = 0) -> str:
        self.calls.append((session_id, generation))
        return f"think-token-{generation}"


def _save_voice_session(session_id: str, repository: FakeSessionRepository) -> None:
    asyncio.run(
        repository.save_session(
            Session(
                id=session_id,
                user_id="demo-user",
                media_id="med_123",
                scene="coffee_shop",
                role="barista",
                opener="Hi there, what can I get started for you today?",
                visual_anchors=["counter", "menu board"],
                vocab_candidates=["latte", "menu"],
                messages=[
                    Message(
                        id="msg_1",
                        role="assistant",
                        text="Hi there, what can I get started for you today?",
                    )
                ],
            )
        )
    )


def test_bootstrap_voice_session_issues_think_token_with_generation(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """配置代理地址时：按代数签发 think 令牌并内嵌 endpoint，fact 落代数 1。"""
    # 显式 pin 配置态：本地 .env 的 ambient 值不得影响用例方向。
    monkeypatch.setattr(
        settings, "deepgram_agent_think_proxy_public_base_url", "https://proxy.example.com"
    )
    _save_voice_session("sess_voice_gen", fake_session_repository)
    settings_builder = FakeVoiceSettingsBuilder()
    think_issuer = FakeThinkTokenIssuer()
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.voice_token_issuer = FakeVoiceTokenIssuer()
    agent.voice_settings_builder = settings_builder
    agent.voice_think_token_issuer = think_issuer

    asyncio.run(agent.bootstrap_voice_session("sess_voice_gen"))

    assert think_issuer.calls == [("sess_voice_gen", 1)]
    assert settings_builder.endpoints == [
        {
            "url": "https://proxy.example.com/api/v1/deepgram/think/chat/completions",
            "headers": {"Authorization": "Bearer think-token-1"},
        }
    ]
    saved_fact = asyncio.run(
        fake_session_repository.get_latest_voice_session_fact("sess_voice_gen")
    )
    assert saved_fact is not None
    assert saved_fact.status == "active"
    assert saved_fact.token_generation == 1


def test_bootstrap_voice_session_increments_generation_on_rebootstrap(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """重复 bootstrap：代数递增，新代数令牌替换旧代数（旧令牌由代理侧拒绝）。"""
    monkeypatch.setattr(
        settings, "deepgram_agent_think_proxy_public_base_url", "https://proxy.example.com"
    )
    _save_voice_session("sess_voice_regen", fake_session_repository)
    settings_builder = FakeVoiceSettingsBuilder()
    think_issuer = FakeThinkTokenIssuer()
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.voice_token_issuer = FakeVoiceTokenIssuer()
    agent.voice_settings_builder = settings_builder
    agent.voice_think_token_issuer = think_issuer

    asyncio.run(agent.bootstrap_voice_session("sess_voice_regen"))
    asyncio.run(agent.bootstrap_voice_session("sess_voice_regen"))

    assert think_issuer.calls == [
        ("sess_voice_regen", 1),
        ("sess_voice_regen", 2),
    ]
    saved_fact = asyncio.run(
        fake_session_repository.get_latest_voice_session_fact("sess_voice_regen")
    )
    assert saved_fact is not None
    assert saved_fact.token_generation == 2


def test_bootstrap_voice_session_skips_think_token_without_proxy_url(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """未配置代理地址（本地开发/托管 open_ai 部署）：不签发不内嵌，行为与历史版本一致。"""
    monkeypatch.setattr(settings, "deepgram_agent_think_proxy_public_base_url", "")
    _save_voice_session("sess_voice_noproxy", fake_session_repository)
    settings_builder = FakeVoiceSettingsBuilder()
    think_issuer = FakeThinkTokenIssuer()
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.voice_token_issuer = FakeVoiceTokenIssuer()
    agent.voice_settings_builder = settings_builder
    agent.voice_think_token_issuer = think_issuer

    asyncio.run(agent.bootstrap_voice_session("sess_voice_noproxy"))

    assert think_issuer.calls == []
    assert settings_builder.endpoints == [None]
    # 代数照常递增：代理是可选路径，计数语义不随门控漂移。
    saved_fact = asyncio.run(
        fake_session_repository.get_latest_voice_session_fact("sess_voice_noproxy")
    )
    assert saved_fact is not None
    assert saved_fact.token_generation == 1


def test_complete_voice_session_preserves_token_generation(
    fake_session_repository: FakeSessionRepository,
    monkeypatch,
) -> None:
    """收口只置状态不清代数：token_generation 必须从既有 fact 回带。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    _save_voice_session("sess_voice_keep_gen", fake_session_repository)
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    asyncio.run(
        fake_session_repository.save_voice_session_fact(
            VoiceSessionFact(
                session_id="sess_voice_keep_gen",
                status="active",
                transcript_turn_count=1,
                token_generation=5,
            )
        )
    )

    asyncio.run(
        agent.complete_voice_session(
            VoiceCompleteInput(
                session_id="sess_voice_keep_gen",
                conversation=[
                    VoiceConversationTurn(
                        role="assistant", content="Hi there, what can I get started for you today?"
                    ),
                    VoiceConversationTurn(
                        role="user", content="Could I get an iced latte, please?"
                    ),
                ],
                termination_reason="user_ended",
            )
        )
    )

    saved_fact = asyncio.run(
        fake_session_repository.get_latest_voice_session_fact("sess_voice_keep_gen")
    )
    assert saved_fact is not None
    assert saved_fact.status == "completed"
    assert saved_fact.token_generation == 5
