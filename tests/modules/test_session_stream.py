"""SessionEngineAgent.stream_reply 事件协议与落库语义直测。"""

from __future__ import annotations

import asyncio
import logging

import pytest

from api.common.exceptions import ModelProviderError
from api.core.config import settings
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.review_builder import ReviewCopy
from api.modules.session_engine.schema import ReplyInput


class RecordingSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.saved_turns: list[tuple[str, Message, Message, object, object]] = []

    async def get_session_head(self, session_id: str) -> Session:
        return self.session

    async def list_recent_messages(self, session_id: str, *, limit: int) -> list[Message]:
        return list(self.session.messages[-limit:])

    async def save_reply_turn(
        self, session_id, learner_message, assistant_message, review, review_copy=None
    ):
        self.saved_turns.append(
            (session_id, learner_message, assistant_message, review, review_copy)
        )
        self.session.messages.extend([learner_message, assistant_message])
        return self.session


class StubFeedbackEngine:
    def __init__(self, result: FeedbackResult | Exception) -> None:
        self._result = result
        self.contexts: list[str | None] = []

    async def review(
        self,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
        learner_context: str | None = None,
    ):
        self.contexts.append(learner_context)
        await asyncio.sleep(0)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class StubCoachStream:
    def __init__(self, chunks: list[str], *, fail_after: int | None = None) -> None:
        self._chunks = chunks
        self._fail_after = fail_after
        self.closed = False

    async def aiter_deltas(self):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index >= self._fail_after:
                raise RuntimeError("stream broke mid-reply")
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class StubCoachEngine:
    def __init__(self, stream: StubCoachStream | Exception) -> None:
        self._stream = stream
        self.calls: list[dict[str, object]] = []

    async def stream_respond(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._stream, Exception):
            raise self._stream
        return self._stream


def _session() -> Session:
    return Session(
        id="sess_stream",
        user_id="demo-user",
        media_id=None,
        scene="coffee_shop",
        role="barista",
        opener="Hi!",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[Message(id="msg_1", role="assistant", text="Hi!")],
    )


def _feedback() -> FeedbackResult:
    return FeedbackResult(
        grammar="Clear enough.",
        more_natural="Could I get a latte?",
        useful_words=["latte"],
    )


def _degraded_feedback_payload() -> dict[str, object]:
    """反馈降级占位文案的契约快照，供流式事件载荷与落库消息双处断言。"""
    return {
        "grammar": "本轮反馈生成失败，请继续对话；下一轮反馈会照常返回。",
        "more_natural": "（本轮没有更自然表达建议）",
        "useful_words": [],
        "errors": [],
        "cefr_level": None,
    }


def _agent(repository, feedback_engine, coach_engine) -> SessionEngineAgent:
    agent = SessionEngineAgent(session_repository=repository)
    agent.feedback_engine = feedback_engine
    agent.coach_engine = coach_engine
    return agent


@pytest.mark.anyio
async def test_stream_reply_emits_feedback_then_deltas_then_session(monkeypatch) -> None:
    # 固定 mock 模式：本测试只关心事件序契约，复盘分支不得发起真实 LLM 调用。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))

    events = [
        event
        async for event in agent.stream_reply(
            ReplyInput(session_id="sess_stream", learner_message="latte please")
        )
    ]

    assert [name for name, _ in events] == ["feedback", "delta", "delta", "session"]
    assert events[0][1].grammar == "Clear enough."
    assert events[1][1] == "Sure, "
    final_session = events[-1][1]
    assert final_session.messages[-1].text == "Sure, one latte."
    assert final_session.messages[-1].feedback == _feedback().model_dump()
    assert len(repository.saved_turns) == 1
    assert stream.closed is True


@pytest.mark.anyio
async def test_stream_reply_degrades_feedback_and_persists_when_feedback_fails(caplog) -> None:
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = _agent(
        repository,
        StubFeedbackEngine(RuntimeError("feedback provider down")),
        StubCoachEngine(stream),
    )

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        events = [
            event
            async for event in agent.stream_reply(
                ReplyInput(session_id="sess_stream", learner_message="latte please")
            )
        ]

    # 反馈失败只降级反馈本身：事件序完整，教练回复照常下发、本轮照常落库。
    assert [name for name, _ in events] == ["feedback", "delta", "delta", "session"]
    assert events[0][1].model_dump() == _degraded_feedback_payload()
    final_session = events[-1][1]
    assert final_session.messages[-1].text == "Sure, one latte."
    assert final_session.messages[-1].feedback == _degraded_feedback_payload()
    assert len(repository.saved_turns) == 1
    assert stream.closed is True
    # 降级必须留运维痕迹：沿用 session_reply_branch_failed 事件名并带 degraded=true。
    assert "session_reply_branch_failed" in caplog.text
    assert "degraded=true" in caplog.text


@pytest.mark.anyio
async def test_stream_reply_aborts_without_persisting_when_coach_open_fails() -> None:
    repository = RecordingSessionRepository(_session())
    agent = _agent(
        repository,
        StubFeedbackEngine(_feedback()),
        StubCoachEngine(RuntimeError("coach open failed")),
    )

    with pytest.raises(RuntimeError, match="coach open failed"):
        _ = [
            event
            async for event in agent.stream_reply(
                ReplyInput(session_id="sess_stream", learner_message="latte please")
            )
        ]

    assert repository.saved_turns == []
    assert len(repository.session.messages) == 1


@pytest.mark.anyio
async def test_stream_reply_aborts_without_persisting_when_stream_breaks_midway(
    monkeypatch,
) -> None:
    # 固定 mock 模式：中途断流时的复盘任务必须被清理，且不得发起真实 LLM 调用。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure,", "one latte."], fail_after=1)
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))

    with pytest.raises(RuntimeError, match="stream broke mid-reply"):
        _ = [
            event
            async for event in agent.stream_reply(
                ReplyInput(session_id="sess_stream", learner_message="latte please")
            )
        ]

    assert repository.saved_turns == []
    assert stream.closed is True


@pytest.mark.anyio
async def test_stream_reply_rejects_empty_coach_output(monkeypatch) -> None:
    # 固定 mock 模式：空回复失败路径的复盘任务必须被清理，且不得发起真实 LLM 调用。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["  "])
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))

    with pytest.raises(ModelProviderError):
        _ = [
            event
            async for event in agent.stream_reply(
                ReplyInput(session_id="sess_stream", learner_message="latte please")
            )
        ]

    assert repository.saved_turns == []


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


class SlowReviewSummarizer:
    """超过有界等待上限的替身：验证超时取消与降级模板复盘。"""

    def __init__(self) -> None:
        self.cancelled = False

    async def summarize(self, **_: object) -> ReviewCopy:
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return ReviewCopy(
            scene_title="x",
            role_label="x",
            highlight="x",
            next_try="x",
            next_step="x",
        )


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


@pytest.mark.anyio
async def test_stream_reply_builds_review_from_llm_copy(monkeypatch) -> None:
    """流式路径复盘与 delta 并行：session 事件与落库 review 消费 LLM 文案。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))
    copy = ReviewCopy(
        scene_title="咖啡店柜台点单",
        role_label="店员对话",
        highlight="这轮你把主需求说完整了。",
        next_try="下一轮补一句杯型或口味细节。",
        next_step="把 useful_words 里的词带进下一轮回答。",
    )
    agent.review_summarizer = summarizer = FakeReviewSummarizer(copy)

    events = [
        event
        async for event in agent.stream_reply(
            ReplyInput(session_id="sess_stream", learner_message="latte please")
        )
    ]

    assert [name for name, _ in events] == ["feedback", "delta", "delta", "session"]
    review = repository.saved_turns[0][3]
    assert review.highlight == "这轮你把主需求说完整了。"
    assert review.next_try == "下一轮补一句杯型或口味细节。"
    assert review.feedback.next_step.body == "把 useful_words 里的词带进下一轮回答。"
    assert summarizer.calls[0]["scene"] == "coffee_shop"
    # LLM 复盘文案原样透传仓储（展示名落库的前提）：与 reply 路径同一契约。
    assert repository.saved_turns[0][4] is copy


@pytest.mark.anyio
async def test_stream_reply_degrades_review_when_summarizer_fails(monkeypatch, caplog) -> None:
    """复盘 LLM 失败只降级模板复盘：事件序完整、本轮照常落库并留 degraded 日志。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))
    agent.review_summarizer = FakeReviewSummarizer(RuntimeError("review provider down"))

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        events = [
            event
            async for event in agent.stream_reply(
                ReplyInput(session_id="sess_stream", learner_message="latte please")
            )
        ]

    assert [name for name, _ in events] == ["feedback", "delta", "delta", "session"]
    review = repository.saved_turns[0][3]
    assert review.highlight.startswith("你已经围绕“咖啡店柜台点单”")
    assert "session_review_copy_failed" in caplog.text
    assert "degraded=true" in caplog.text
    # 降级轮透传 None：仓储不触碰展示名列，保留上一次有效值（不回闪）。
    assert repository.saved_turns[0][4] is None


@pytest.mark.anyio
async def test_stream_reply_cancels_slow_review_task_and_degrades(monkeypatch, caplog) -> None:
    """复盘超过 llm_review_wait_seconds 未返回：取消任务并降级模板复盘。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    monkeypatch.setattr(settings, "llm_review_wait_seconds", 0.05)
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))
    summarizer = SlowReviewSummarizer()
    agent.review_summarizer = summarizer

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        events = [
            event
            async for event in agent.stream_reply(
                ReplyInput(session_id="sess_stream", learner_message="latte please")
            )
        ]

    assert [name for name, _ in events] == ["feedback", "delta", "delta", "session"]
    review = repository.saved_turns[0][3]
    assert review.highlight.startswith("你已经围绕“咖啡店柜台点单”")
    assert "session_review_copy_failed" in caplog.text
    # 给事件循环几个 tick，让取消请求在慢速任务内落地。
    for _ in range(10):
        if summarizer.cancelled:
            break
        await asyncio.sleep(0)
    assert summarizer.cancelled is True


@pytest.mark.anyio
async def test_stream_reply_skips_review_task_when_feedback_degraded(monkeypatch) -> None:
    """feedback 已降级时不起复盘任务：summarizer 不得被调用。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    _pin_live_fake_provider_slots(monkeypatch)
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = _agent(
        repository,
        StubFeedbackEngine(RuntimeError("feedback provider down")),
        StubCoachEngine(stream),
    )
    summarizer = FakeReviewSummarizer(
        ReviewCopy(
            scene_title="x",
            role_label="x",
            highlight="x",
            next_try="x",
            next_step="x",
        )
    )
    agent.review_summarizer = summarizer

    events = [
        event
        async for event in agent.stream_reply(
            ReplyInput(session_id="sess_stream", learner_message="latte please")
        )
    ]

    assert [name for name, _ in events] == ["feedback", "delta", "delta", "session"]
    assert summarizer.calls == []
    assert events[0][1].model_dump() == _degraded_feedback_payload()


class FakeLearnerProfileRepository:
    """实现 LearnerProfileRepository 协议的内存替身，记录全部写入。"""

    def __init__(self, *, fail_on_upsert: bool = False) -> None:
        self.profiles: dict[str, object] = {}
        self.upsert_calls: list[str] = []
        self._fail_on_upsert = fail_on_upsert

    async def get(self, user_id: str):
        return self.profiles.get(user_id)

    async def upsert(self, profile):
        if self._fail_on_upsert:
            raise RuntimeError("profile store unavailable")
        self.upsert_calls.append(profile.user_id)
        self.profiles[profile.user_id] = profile
        return profile


@pytest.mark.anyio
async def test_stream_reply_updates_learner_profile_before_session_event(monkeypatch) -> None:
    """session 事件下发之前本轮档案已落档（更新在 yield 之前）。"""
    # 固定 mock 模式：本地 .env 是 live 模式，不 pin 会打真 LLM。
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    session = _session().model_copy(update={"user_id": "user:42"})
    repository = RecordingSessionRepository(session)
    profile_repository = FakeLearnerProfileRepository()
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = SessionEngineAgent(
        session_repository=repository,
        learner_profile_repository=profile_repository,
    )
    agent.feedback_engine = StubFeedbackEngine(_feedback())
    agent.coach_engine = StubCoachEngine(stream)

    event_names: list[str] = []
    async for name, _payload in agent.stream_reply(
        ReplyInput(session_id="sess_stream", learner_message="latte please")
    ):
        event_names.append(name)
        if name == "session":
            assert "user:42" in profile_repository.profiles

    assert event_names == ["feedback", "delta", "delta", "session"]
    profile = profile_repository.profiles["user:42"]
    assert profile.practiced_turn_count == 1
    assert profile.scene_counts == {"coffee_shop": 1}
    # 落库先于档案更新：save_reply_turn 成功是档案累积的前置条件。
    assert len(repository.saved_turns) == 1
    assert profile_repository.upsert_calls == ["user:42"]


@pytest.mark.anyio
async def test_stream_reply_completes_when_profile_upsert_fails(monkeypatch, caplog) -> None:
    """档案写失败是增强分支故障：事件序不变、本轮照常落库，留 degraded 日志。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    session = _session().model_copy(update={"user_id": "user:42"})
    repository = RecordingSessionRepository(session)
    profile_repository = FakeLearnerProfileRepository(fail_on_upsert=True)
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = SessionEngineAgent(
        session_repository=repository,
        learner_profile_repository=profile_repository,
    )
    agent.feedback_engine = StubFeedbackEngine(_feedback())
    agent.coach_engine = StubCoachEngine(stream)

    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.agent"):
        events = [
            event
            async for event in agent.stream_reply(
                ReplyInput(session_id="sess_stream", learner_message="latte please")
            )
        ]

    assert [name for name, _ in events] == ["feedback", "delta", "delta", "session"]
    assert events[-1][1].messages[-1].text == "Sure, one latte."
    assert len(repository.saved_turns) == 1
    assert stream.closed is True
    assert "learner_profile_update_failed" in caplog.text
    assert "degraded=true" in caplog.text
