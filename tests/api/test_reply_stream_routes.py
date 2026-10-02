"""/sessions/{id}/reply/stream SSE 路由测试：帧序、错误收敛、开流前置校验。"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from api.common.exceptions import ModelProviderError, NotFoundError
from api.main import app
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult
from api.routes.v1.sessions import get_llm_rate_limiter, get_session_service
from api.services.llm_rate_limit import InMemoryLLMRateLimiter, LLMRateLimitRule


def _session() -> Session:
    return Session(
        id="sess_stream",
        user_id="visitor:v-1",
        media_id=None,
        scene="coffee_shop",
        role="barista",
        opener="Hi!",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[Message(id="msg_1", role="assistant", text="Hi!")],
    )


class FakeReplyStreamService:
    def __init__(self) -> None:
        self.prepared: list[tuple[str, str, str | None]] = []
        self.fail_after: str | None = None

    async def prepare_reply_stream(
        self,
        session_id: str,
        learner_message: str,
        owner_id: str | None = None,
    ) -> AsyncIterator[tuple[str, object]]:
        self.prepared.append((session_id, learner_message, owner_id))
        if session_id == "sess_missing":
            raise NotFoundError(f"Session {session_id} not found")
        return self._events()

    async def _events(self) -> AsyncIterator[tuple[str, object]]:
        yield (
            "feedback",
            FeedbackResult(grammar="Clear.", more_natural="Latte, please.", useful_words=["latte"]),
        )
        yield ("delta", "Sure, ")
        if self.fail_after == "delta":
            raise ModelProviderError("Coach provider exploded")
        yield ("delta", "one latte.")
        session = _session()
        session.messages.append(Message(id="msg_2", role="user", text="latte please"))
        session.messages.append(
            Message(
                id="msg_3",
                role="assistant",
                text="Sure, one latte.",
                feedback={
                    "grammar": "Clear.",
                    "more_natural": "Latte, please.",
                    "useful_words": ["latte"],
                },
            )
        )
        yield ("session", session)

    async def reply_to_session(self, session_id: str, learner_message: str, owner_id=None):
        session = _session()
        session.messages.extend(
            [
                Message(id="msg_2", role="user", text=learner_message),
                Message(
                    id="msg_3",
                    role="assistant",
                    text="Sure, one latte.",
                    feedback={
                        "grammar": "Clear.",
                        "more_natural": "Latte, please.",
                        "useful_words": ["latte"],
                    },
                ),
            ]
        )
        return session


@pytest.fixture
def client():
    service = FakeReplyStreamService()
    app.dependency_overrides[get_session_service] = lambda: service
    # 限流器必须是同一个实例：lambda 内重建会让每次请求都拿到全新计数。
    # 显式规则即完整规则集：匿名请求还会消耗 IP 兜底键（reply_ip /
    # session_start_ip），规则集必须一并给出，否则 _resolve_rule 会 KeyError。
    limiter = InMemoryLLMRateLimiter(
        rules={
            "reply": LLMRateLimitRule(limit=5, window_seconds=3600),
            "session_start": LLMRateLimitRule(limit=5, window_seconds=3600),
            "reply_ip": LLMRateLimitRule(limit=100, window_seconds=3600),
            "session_start_ip": LLMRateLimitRule(limit=100, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter
    with TestClient(app) as test_client:
        yield test_client, service
    app.dependency_overrides.clear()


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
        assert data_lines, f"frame without data: {frame!r}"
        import json

        frames.append((event_name, json.loads("\n".join(data_lines))))
    return frames


def test_reply_stream_emits_feedback_deltas_then_final_session(client) -> None:
    test_client, service = client

    response = test_client.post(
        "/api/v1/sessions/sess_stream/reply/stream",
        json={"learner_message": "latte please"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _parse_sse(response.text)
    assert [name for name, _ in frames] == ["feedback", "delta", "delta", "session"]

    feedback_payload = frames[0][1]
    assert feedback_payload["grammar"] == "Clear."
    assert frames[1][1] == {"text": "Sure, "}
    final = frames[-1][1]
    assert final["session"]["session_id"] == "sess_stream"
    assert final["session"]["messages"][-1]["text"] == "Sure, one latte."
    assert final["session"]["messages"][-1]["feedback"]["grammar"] == "Clear."
    assert final["feedback"]["more_natural"] == "Latte, please."
    # 所有权沿用同一 owner 上下文（visitor 或 user）。
    assert service.prepared[0][0] == "sess_stream"


def test_reply_stream_maps_business_error_to_error_event(client) -> None:
    test_client, service = client
    service.fail_after = "delta"

    response = test_client.post(
        "/api/v1/sessions/sess_stream/reply/stream",
        json={"learner_message": "latte please"},
    )

    assert response.status_code == 200  # 已开流，错误走事件而非状态码
    frames = _parse_sse(response.text)
    assert [name for name, _ in frames] == ["feedback", "delta", "error"]
    error_payload = frames[-1][1]
    assert error_payload["code"] == 1005
    assert error_payload["message"] == "Coach provider exploded"


def test_reply_stream_validation_and_missing_session_stay_json_envelope(client) -> None:
    test_client, _ = client

    missing = test_client.post(
        "/api/v1/sessions/sess_missing/reply/stream",
        json={"learner_message": "latte please"},
    )
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")
    assert missing.json()["code"] == 1004

    empty = test_client.post(
        "/api/v1/sessions/sess_stream/reply/stream",
        json={"learner_message": "   "},
    )
    assert empty.status_code == 400
    assert empty.json()["code"] == 1001


def test_reply_stream_rate_limit_returns_envelope_before_streaming(client) -> None:
    test_client, _ = client
    for _ in range(5):
        test_client.post(
            "/api/v1/sessions/sess_stream/reply/stream",
            json={"learner_message": "latte please"},
        )

    limited = test_client.post(
        "/api/v1/sessions/sess_stream/reply/stream",
        json={"learner_message": "latte please"},
    )
    assert limited.status_code == 429
    assert limited.headers["content-type"].startswith("application/json")
    assert limited.json()["code"] == 1006


def test_legacy_json_reply_endpoint_still_works(client) -> None:
    test_client, _service = client

    response = test_client.post(
        "/api/v1/sessions/sess_stream/reply",
        json={"learner_message": "latte please"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session"]["messages"][-1]["text"] == "Sure, one latte."
    assert body["data"]["feedback"]["grammar"] == "Clear."
