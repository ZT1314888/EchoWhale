"""SessionEngineAgent.stream_reply 事件协议与落库语义直测。"""

from __future__ import annotations

import asyncio
import logging

import pytest

from api.common.exceptions import ModelProviderError
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.schema import ReplyInput


class RecordingSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.saved_turns: list[tuple[str, Message, Message, object]] = []

    async def get_session_head(self, session_id: str) -> Session:
        return self.session

    async def list_recent_messages(self, session_id: str, *, limit: int) -> list[Message]:
        return list(self.session.messages[-limit:])

    async def save_reply_turn(self, session_id, learner_message, assistant_message, review):
        self.saved_turns.append((session_id, learner_message, assistant_message, review))
        self.session.messages.extend([learner_message, assistant_message])
        return self.session


class StubFeedbackEngine:
    def __init__(self, result: FeedbackResult | Exception) -> None:
        self._result = result

    async def review(self, learner_message: str, scene: str, vocab_candidates: list[str]):
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
    }


def _agent(repository, feedback_engine, coach_engine) -> SessionEngineAgent:
    agent = SessionEngineAgent(session_repository=repository)
    agent.feedback_engine = feedback_engine
    agent.coach_engine = coach_engine
    return agent


@pytest.mark.anyio
async def test_stream_reply_emits_feedback_then_deltas_then_session() -> None:
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure, ", "one latte."])
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))

    events = [event async for event in agent.stream_reply(ReplyInput(session_id="sess_stream", learner_message="latte please"))]

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
        _ = [event async for event in agent.stream_reply(ReplyInput(session_id="sess_stream", learner_message="latte please"))]

    assert repository.saved_turns == []
    assert len(repository.session.messages) == 1


@pytest.mark.anyio
async def test_stream_reply_aborts_without_persisting_when_stream_breaks_midway() -> None:
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["Sure,", "one latte."], fail_after=1)
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))

    with pytest.raises(RuntimeError, match="stream broke mid-reply"):
        _ = [event async for event in agent.stream_reply(ReplyInput(session_id="sess_stream", learner_message="latte please"))]

    assert repository.saved_turns == []
    assert stream.closed is True


@pytest.mark.anyio
async def test_stream_reply_rejects_empty_coach_output() -> None:
    repository = RecordingSessionRepository(_session())
    stream = StubCoachStream(["  "])
    agent = _agent(repository, StubFeedbackEngine(_feedback()), StubCoachEngine(stream))

    with pytest.raises(ModelProviderError):
        _ = [event async for event in agent.stream_reply(ReplyInput(session_id="sess_stream", learner_message="latte please"))]

    assert repository.saved_turns == []
