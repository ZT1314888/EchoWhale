"""mock 模式全栈 e2e：start → reply / reply-stream 的三层 span 树（server/engine/attempt）。

复用 tests/api 既有 dependency_overrides 套路：真实 SessionEngineService 编排 +
内存仓储替身，引擎走 MODEL_RUNTIME_MODE=mock 的 mock providers（零真实网络、
零真实 DB）。span 收集经 conftest 的 recording_tracer（独立 SDK provider，
绝不触碰全局 set_tracer_provider）。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace

from api.main import app
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.session_engine.service import SessionEngineService
from api.routes.v1.sessions import get_llm_rate_limiter, get_session_service
from api.services.llm_rate_limit import InMemoryLLMRateLimiter, LLMRateLimitRule


class InMemorySessionRepository:
    """编排层所需的内存仓储替身：start/reply 路径的最小方法集。"""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.span_recordings: list[bool] = []

    async def save_session(self, session: Session) -> Session:
        self.sessions[session.id] = session
        return session

    async def get_session(self, session_id: str) -> Session:
        return self.sessions[session_id]

    async def get_session_head(self, session_id: str) -> Session:
        return self.sessions[session_id]

    async def list_recent_messages(self, session_id: str, *, limit: int) -> list[Message]:
        return list(self.sessions[session_id].messages[-limit:])

    async def save_reply_turn(
        self,
        session_id: str,
        learner_message: Message,
        assistant_message: Message,
        review: Any,
        review_copy: Any = None,
    ) -> Session:
        # 顺带探测落库时 current span 是否在记录（关闭态锁定用）。
        self.span_recordings.append(trace.get_current_span().is_recording())
        session = self.sessions[session_id]
        session.messages.extend([learner_message, assistant_message])
        self.sessions[session_id] = session
        return session


def _generous_limiter() -> InMemoryLLMRateLimiter:
    # 显式规则即完整规则集：匿名请求还会消耗 IP 兜底键，规则集必须一并给出。
    return InMemoryLLMRateLimiter(
        rules={
            "reply": LLMRateLimitRule(limit=100, window_seconds=3600),
            "session_start": LLMRateLimitRule(limit=100, window_seconds=3600),
            "reply_ip": LLMRateLimitRule(limit=1000, window_seconds=3600),
            "session_start_ip": LLMRateLimitRule(limit=1000, window_seconds=3600),
        }
    )


@pytest.fixture
def e2e_client(
    recording_tracer,
) -> Iterator[tuple[TestClient, InMemorySessionRepository, Any]]:
    """真实编排 + 内存仓储：mock 引擎全链路，span 落内存导出器（recording_tracer）。"""
    repository = InMemorySessionRepository()
    service = SessionEngineService(session_repository=repository)
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_llm_rate_limiter] = lambda: _generous_limiter()
    try:
        with TestClient(app) as test_client:
            yield test_client, repository, recording_tracer
    finally:
        app.dependency_overrides.clear()


def _spans_named(exporter: Any, name: str) -> list[Any]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


def _one_span(exporter: Any, name: str) -> Any:
    spans = _spans_named(exporter, name)
    assert len(spans) == 1, f"expected exactly one {name}, got {len(spans)}"
    return spans[0]


def _start_sample_session(client: TestClient) -> str:
    response = client.post("/api/v1/sessions", json={"sample_scene_id": "coffee"})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    return body["data"]["session_id"]


def _assert_request_id_linked(spans: list[Any], request_id: str) -> None:
    for span in spans:
        assert span.attributes["echowhale.request_id"] == request_id, span.name


# ---------- start：样例预设无 engine span（预期边界） ----------


def test_start_sample_session_has_server_span_without_engine_spans(e2e_client) -> None:
    client, _repository, exporter = e2e_client

    response = client.post("/api/v1/sessions", json={"sample_scene_id": "coffee"})

    session_id = response.json()["data"]["session_id"]
    assert session_id
    spans = list(exporter.get_finished_spans())
    # 样例预设路径不经过任何引擎分支：只有 server span。
    assert [span.name for span in spans] == ["HTTP POST /api/v1/sessions"]
    server = spans[0]
    assert server.attributes["http.route"] == "/api/v1/sessions"
    assert server.attributes["http.status_code"] == 200
    assert server.attributes["echowhale.terminal"] == "ok"
    assert server.attributes["echowhale.request_id"] == response.headers["x-request-id"]
    assert server.parent is None


# ---------- reply：server 包 engine，engine 包 attempt ----------


def test_reply_full_stack_span_tree(e2e_client) -> None:
    client, _repository, exporter = e2e_client
    session_id = _start_sample_session(client)

    response = client.post(
        f"/api/v1/sessions/{session_id}/reply",
        json={"learner_message": "I would like a latte, please."},
    )

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]

    server = _one_span(exporter, "HTTP POST /api/v1/sessions/{session_id}/reply")
    feedback = _one_span(exporter, "engine.feedback")
    coach = _one_span(exporter, "engine.coach")
    review = _one_span(exporter, "engine.review")
    attempts = _spans_named(exporter, "llm.attempt")
    # mock 模式下反馈分支短路（不经历 failover），只有教练分支产生 attempt span。
    assert len(attempts) == 1

    # 父子关系：engine 挂 server，attempt 挂各自 engine。
    assert server.parent is None
    for engine in (feedback, coach, review):
        assert engine.parent.span_id == server.context.span_id
    (coach_attempt,) = attempts
    assert coach_attempt.parent.span_id == coach.context.span_id
    assert coach_attempt.attributes["llm.attempt.name"] == "text_primary"

    # 终态映射（design 2.3）：feedback ok、coach ok、review 在 mock 短路下降级。
    assert feedback.attributes["echowhale.terminal"] == "ok"
    assert coach.attributes["echowhale.terminal"] == "ok"
    assert review.attributes["echowhale.terminal"] == "degraded"
    assert coach_attempt.attributes["echowhale.terminal"] == "ok"

    # request-id 跨层贯穿：响应头与全部 span 属性一致。
    _assert_request_id_linked([server, feedback, coach, review, *attempts], request_id)


# ---------- reply/stream：教练 span 只覆盖开流 ----------


def test_stream_reply_span_tree_and_server_terminal(e2e_client) -> None:
    client, _repository, exporter = e2e_client
    session_id = _start_sample_session(client)

    response = client.post(
        f"/api/v1/sessions/{session_id}/reply/stream",
        json={"learner_message": "One iced latte please."},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert body.index("event: feedback") < body.index("event: delta")
    assert "event: session" in body

    server = _one_span(exporter, "HTTP POST /api/v1/sessions/{session_id}/reply/stream")
    assert server.attributes["echowhale.terminal"] == "ok"
    feedback = _one_span(exporter, "engine.feedback")
    coach = _one_span(exporter, "engine.coach")
    review = _one_span(exporter, "engine.review")
    assert feedback.attributes["echowhale.terminal"] == "ok"
    assert coach.attributes["echowhale.terminal"] == "ok"
    assert review.attributes["echowhale.terminal"] == "degraded"
    # 流式路径的教练 span 只覆盖开流（跨 yield 会泄漏中间态，明确不做）：
    # 消费耗时由 server span 承载，这里断言 coach/engine 均正常收口并导出。
    assert coach.parent.span_id == server.context.span_id


# ---------- 关闭态：全链路零记录 span ----------


def test_closed_state_full_stack_records_nothing() -> None:
    """默认配置（otel_enabled=False）：真实编排全链路 current span 一律不记录。"""
    repository = InMemorySessionRepository()
    service = SessionEngineService(session_repository=repository)
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_llm_rate_limiter] = lambda: _generous_limiter()
    try:
        with TestClient(app) as client:
            started = client.post("/api/v1/sessions", json={"sample_scene_id": "coffee"})
            assert started.status_code == 200
            session_id = started.json()["data"]["session_id"]
            replied = client.post(
                f"/api/v1/sessions/{session_id}/reply",
                json={"learner_message": "Latte, please."},
            )
            assert replied.status_code == 200
    finally:
        app.dependency_overrides.clear()

    # 落库（链路最深处）探测：current span 从未进入 recording。
    assert repository.span_recordings == [False]
