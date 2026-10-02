from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.common.exceptions import AuthenticationError
from api.common.exceptions import NotFoundError
from api.common.exceptions import SceneAnalysisUnavailableError
from api.common.exceptions import UnsupportedSceneImageError
from api.common.exceptions import VoiceTokenError
from api.core.config import settings
from api.core.security import sign_value, verify_signed_value
from api.main import app
from api.models.message_model import Message
from api.models.session_model import Session
from api.models.user_model import User

try:
    from api.routes.v1.auth import get_auth_service
    from api.routes.v1.sessions import get_session_service
except ImportError:  # pragma: no cover - expected during red phase
    get_auth_service = None
    get_session_service = None

from api.services.llm_rate_limit import InMemoryLLMRateLimiter, LLMRateLimitRule, get_llm_rate_limiter


class FakeSessionService:
    def __init__(self) -> None:
        earlier = datetime(2026, 4, 4, 15, 20, tzinfo=timezone.utc)
        later = earlier + timedelta(hours=2)
        self.sessions = {
            "sess_123": Session(
                id="sess_123",
                user_id="user:user_123",
                media_id="med_123",
                scene="coffee_shop",
                role="barista",
                opener="Hi there, what can I get started for you today?",
                visual_anchors=["counter", "menu board"],
                vocab_candidates=["coffee", "order"],
                messages=[
                    Message(
                        id="msg_1",
                        role="assistant",
                        text="Hi there, what can I get started for you today?",
                    )
                ],
                created_at=earlier,
                updated_at=earlier,
            ),
            "sess_456": Session(
                id="sess_456",
                user_id="user:user_123",
                media_id="med_789",
                scene="office",
                role="teammate",
                opener="Can you give me a quick status update?",
                visual_anchors=["glass wall", "meeting room"],
                vocab_candidates=["update", "timeline"],
                messages=[
                    Message(
                        id="msg_10",
                        role="assistant",
                        text="Can you give me a quick status update?",
                    ),
                    Message(
                        id="msg_11",
                        role="user",
                        text="We shipped authentication, and upload is in progress.",
                    ),
                    Message(
                        id="msg_12",
                        role="assistant",
                        text="Nice. Can you share expected completion date?",
                    ),
                ],
                created_at=later,
                updated_at=later,
            ),
            "sess_no_review": Session(
                id="sess_no_review",
                user_id="user:user_123",
                media_id="med_456",
                scene="office",
                role="teammate",
                opener="Can you give me a quick status update?",
                visual_anchors=["glass wall", "sofa"],
                vocab_candidates=["update", "deadline"],
                messages=[
                    Message(
                        id="msg_pending_1",
                        role="assistant",
                        text="Can you give me a quick status update?",
                    )
                ],
                created_at=later + timedelta(minutes=5),
                updated_at=later + timedelta(minutes=5),
            ),
        }
        self.reviews = {
            "sess_123": SimpleNamespace(
                session_id="sess_123",
                title="本轮回响",
                highlight="你已经说清楚主要需求，表达比上一轮更稳定。",
                next_try="下一轮先说主需求，再补一条口味或杯型细节。",
                feedback=SimpleNamespace(
                    grammar=SimpleNamespace(title="Grammar", body="Your meaning is clear."),
                    more_natural=SimpleNamespace(
                        title="More Natural",
                        body="Could I get an iced latte, please?",
                    ),
                    useful_words=SimpleNamespace(
                        title="Useful Words",
                        words=["latte", "size", "iced"],
                        body="把这些词带进下一轮回答，会更自然。",
                    ),
                    next_step=SimpleNamespace(
                        title="Next Step",
                        body="下一轮试着在一句主回应后再补一句细节。",
                    ),
                ),
            ),
            "sess_456": SimpleNamespace(
                session_id="sess_456",
                title="本轮复盘",
                highlight="你先说结果再补进度，结构更清楚。",
                next_try="下一轮补一句风险或阻塞，会更完整。",
                feedback=SimpleNamespace(
                    grammar=SimpleNamespace(title="Grammar", body="Tense usage is clear."),
                    more_natural=SimpleNamespace(
                        title="More Natural",
                        body="We have finished auth and upload is still in progress.",
                    ),
                    useful_words=SimpleNamespace(
                        title="Useful Words",
                        words=["progress", "timeline", "blocker"],
                        body="把这些词带进状态汇报会更专业。",
                    ),
                    next_step=SimpleNamespace(
                        title="Next Step",
                        body="下一轮试着加入一句风险说明。",
                    ),
                ),
            ),
        }

    async def start_session(
        self,
        user_id: str,
        media_id: str | None = None,
        sample_scene_id: str | None = None,
    ) -> Session:
        assert user_id == "user:user_123"
        if sample_scene_id is not None:
            session = Session(
                id="sess_sample_created",
                user_id=user_id,
                media_id=None,
                scene="coffee_shop",
                role="friendly barista",
                opener="Hello! What would you like to order today?",
                visual_anchors=["counter", "pastry case"],
                vocab_candidates=["latte", "size"],
                messages=[
                    Message(
                        id="msg_sample_1",
                        role="assistant",
                        text="Hello! What would you like to order today?",
                    )
                ],
            )
            self.sessions[session.id] = session
            return session

        session = Session(
            id="sess_created",
            user_id=user_id,
            media_id=media_id,
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            visual_anchors=["counter", "menu board"],
            vocab_candidates=["coffee", "order"],
            messages=[
                Message(
                    id="msg_created_1",
                    role="assistant",
                    text="Hi there, what can I get started for you today?",
                )
            ],
        )
        self.sessions[session.id] = session
        return session

    async def get_session(self, session_id: str, owner_id: str | None = None) -> Session:
        assert owner_id in (None, "user:user_123")
        session = self.sessions.get(session_id)
        if session is None:
            raise NotFoundError(f"Session {session_id} not found")
        return session

    async def reply_to_session(
        self,
        session_id: str,
        learner_message: str,
        owner_id: str | None = None,
    ) -> Session:
        assert owner_id in (None, "user:user_123")
        session = await self.get_session(session_id)
        session.messages.append(
            Message(
                id="msg_2",
                role="user",
                text=learner_message,
            )
        )
        session.messages.append(
            Message(
                id="msg_3",
                role="assistant",
                text="Sure. What size would you like?",
                feedback={
                    "grammar": "Your meaning is clear.",
                    "more_natural": "Could I get an iced latte, please?",
                    "useful_words": ["latte", "size", "iced"],
                },
            )
        )
        return session

    async def get_session_review(self, session_id: str, owner_id: str | None = None):
        assert owner_id in (None, "user:user_123")
        review = self.reviews.get(session_id)
        if review is None:
            raise NotFoundError(f"Session review {session_id} not found")
        return review

    async def list_history_sessions(self, user_id: str) -> list[Session]:
        assert user_id == "user:user_123"
        return list(self.sessions.values())

    async def list_history_sessions_page(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Session], str | None, bool]:
        assert user_id == "user:user_123"
        ordered = [
            self.sessions["sess_456"],
            self.sessions["sess_123"],
        ]
        start = 0
        if cursor is not None:
            ids = [session.id for session in ordered]
            start = ids.index(cursor) + 1 if cursor in ids else len(ordered)
        page = ordered[start : start + limit]
        has_more = (start + limit) < len(ordered)
        next_cursor = page[-1].id if has_more and page else None
        return (page, has_more, next_cursor)

    async def list_history_reviews(self, session_ids: list[str]):
        return {
            session_id: review
            for session_id, review in self.reviews.items()
            if session_id in session_ids
        }

    async def get_history_session_overview(self, user_id: str, session_id: str):
        assert user_id == "user:user_123"
        session = await self.get_session(session_id)
        review = await self.get_session_review(session_id)
        return (session, review, len(session.messages))

    async def list_history_session_messages(
        self,
        user_id: str,
        session_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Message], bool, str | None]:
        assert user_id == "user:user_123"
        session = await self.get_session(session_id)
        messages = list(session.messages)
        if cursor is not None:
            ids = [message.id for message in messages]
            cutoff = ids.index(cursor) if cursor in ids else 0
            messages = messages[:cutoff]
        start = max(len(messages) - limit, 0)
        page = messages[start:]
        has_more = start > 0
        next_before = page[0].id if has_more and page else None
        return (page, has_more, next_before)

    async def get_history_session_detail(self, user_id: str, session_id: str):
        assert user_id == "user:user_123"
        session = await self.get_session(session_id)
        review = await self.get_session_review(session_id)
        return (session, review)

    async def bootstrap_voice_session(self, session_id: str, owner_id: str | None = None):
        assert owner_id in (None, "user:user_123")
        session = await self.get_session(session_id)
        return {
            "session_id": session.id,
            "deepgram_access_token": "dg-token",
            "expires_in": 600,
            "deepgram_ws_url": "wss://api.deepgram.com/v1/agent/converse",
            "agent_settings": {
                "type": "Settings",
                "agent": {
                    "language": "en",
                    "greeting": session.opener,
                },
            },
            "session": session,
        }

    async def complete_voice_session(
        self,
        session_id: str,
        conversation,
        termination_reason: str,
        client_diagnostics: dict[str, object] | None = None,
        owner_id: str | None = None,
    ):
        assert owner_id in (None, "user:user_123")
        assert termination_reason == "user_ended"
        assert client_diagnostics == {}
        session = await self.get_session(session_id)
        session.messages = [
            Message(id="msg_1", role="assistant", text="Hi there, what can I get started for you today?"),
            Message(id="msg_2", role="user", text="Could I get an iced latte, please?"),
            Message(id="msg_3", role="assistant", text="Of course. What size would you like?"),
        ]
        self.sessions[session_id] = session
        review = await self.get_session_review("sess_123")
        self.reviews[session_id] = review
        return {"session": session, "review": review}


class FakeAuthService:
    def get_current_user(self, *, access_token: str) -> User:
        if access_token != "valid-access-token":
            raise AuthenticationError("Authentication required")
        return User(id="user_123", email="learner@example.com", nickname="Echo Learner")


class UnsupportedSessionService:
    async def start_session(
        self,
        user_id: str,
        media_id: str | None = None,
        sample_scene_id: str | None = None,
    ) -> Session:
        raise UnsupportedSceneImageError(
            "Unsupported scene image",
            data={"reason": "image_too_uniform", "retryable": False},
        )


class UnavailableSceneSessionService:
    async def start_session(
        self,
        user_id: str,
        media_id: str | None = None,
        sample_scene_id: str | None = None,
    ) -> Session:
        raise SceneAnalysisUnavailableError()


class VoiceBootstrapFailureSessionService(FakeSessionService):
    async def bootstrap_voice_session(self, session_id: str, owner_id: str | None = None):
        raise VoiceTokenError()


class VisitorAwareSessionService(FakeSessionService):
    """匿名访客场景专用替身：owner_id 随 Cookie 变化，不固定为 user:user_123。

    记录每次请求看到的 owner_id，供测试断言伪造 Cookie 值没有进入身份链路。
    """

    def __init__(self) -> None:
        super().__init__()
        self.seen_owner_ids: list[str | None] = []

    async def start_session(
        self,
        user_id: str,
        media_id: str | None = None,
        sample_scene_id: str | None = None,
    ) -> Session:
        self.seen_owner_ids.append(user_id)
        session = Session(
            id=f"sess_visitor_{len(self.seen_owner_ids)}",
            user_id=user_id,
            media_id=media_id,
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            visual_anchors=["counter", "menu board"],
            vocab_candidates=["coffee", "order"],
            messages=[
                Message(
                    id=f"msg_visitor_{len(self.seen_owner_ids)}",
                    role="assistant",
                    text="Hi there, what can I get started for you today?",
                )
            ],
        )
        self.sessions[session.id] = session
        return session

    async def get_session(self, session_id: str, owner_id: str | None = None) -> Session:
        self.seen_owner_ids.append(owner_id)
        session = self.sessions.get(session_id)
        if session is None:
            raise NotFoundError(f"Session {session_id} not found")
        return session


class RecordingDeepgramTokenIssuer:
    """记录 Deepgram token 签发次数的假 issuer。

    真实链路里 grant 发生在 agent 内部（route → service → agent → issuer）；
    fake 在 service 替身里调用它，保证"限流通过才签发"能被断言。
    """

    def __init__(self) -> None:
        self.grant_calls = 0

    def issue_token(self, ttl_seconds: int) -> tuple[str, float]:
        self.grant_calls += 1
        return (f"fake-dg-token-{self.grant_calls}", float(ttl_seconds))


class IssuerBackedVoiceSessionService(FakeSessionService):
    """bootstrap 时经由 fake issuer 签发令牌的语音会话服务替身。

    不沿用父类 bootstrap 的 owner 断言：匿名访客（owner=visitor:*）也要能
    走通 bootstrap，供 IP 兜底键的轮换 Cookie 测试使用。
    """

    def __init__(self, issuer: RecordingDeepgramTokenIssuer) -> None:
        super().__init__()
        self.issuer = issuer

    async def bootstrap_voice_session(self, session_id: str, owner_id: str | None = None):
        session = self.sessions.get(session_id)
        if session is None:
            raise NotFoundError(f"Session {session_id} not found")
        token, expires_in = self.issuer.issue_token(settings.deepgram_agent_token_ttl_seconds)
        return {
            "session_id": session.id,
            "deepgram_access_token": token,
            "expires_in": expires_in,
            "deepgram_ws_url": "wss://api.deepgram.com/v1/agent/converse",
            "agent_settings": {
                "type": "Settings",
                "agent": {
                    "language": "en",
                    "greeting": session.opener,
                },
            },
            "session": session,
        }


@pytest.fixture(autouse=True)
def clear_session_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    if get_session_service is not None:
        app.dependency_overrides[get_session_service] = lambda: FakeSessionService()
    if get_auth_service is not None:
        app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    app.dependency_overrides[get_llm_rate_limiter] = lambda: InMemoryLLMRateLimiter()

    with TestClient(app) as test_client:
        yield test_client


def test_start_session_returns_created_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={"media_id": "med_123"},
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session_id"] == "sess_created"
    assert body["data"]["media_id"] == "med_123"
    assert body["data"]["scene"] == "coffee_shop"
    assert body["data"]["visual_anchors"] == ["counter", "menu board"]
    assert body["data"]["vocab_candidates"] == ["coffee", "order"]
    assert body["data"]["messages"][0]["message_id"] == "msg_created_1"


def test_start_sample_session_returns_created_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={"sample_scene_id": "coffee"},
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session_id"] == "sess_sample_created"
    assert body["data"]["media_id"] is None
    assert body["data"]["scene"] == "coffee_shop"
    assert body["data"]["role"] == "friendly barista"
    assert body["data"]["messages"][0]["text"] == "Hello! What would you like to order today?"


def test_start_session_rejects_payload_with_both_media_and_sample(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={"media_id": "med_123", "sample_scene_id": "coffee"},
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
    assert response.json()["message"] == "Validation error"


def test_start_session_returns_unsupported_scene_image_error(client: TestClient) -> None:
    assert get_session_service is not None
    app.dependency_overrides[get_session_service] = lambda: UnsupportedSessionService()

    response = client.post(
        "/api/v1/sessions",
        json={"media_id": "med_black"},
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": 1007,
        "message": "Unsupported scene image",
        "data": {
            "reason": "image_too_uniform",
            "retryable": False,
        },
    }


def test_start_session_returns_scene_analysis_unavailable_error(client: TestClient) -> None:
    assert get_session_service is not None
    app.dependency_overrides[get_session_service] = lambda: UnavailableSceneSessionService()

    response = client.post(
        "/api/v1/sessions",
        json={"media_id": "med_busy"},
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": 1008,
        "message": "图片分析暂时不可用，请稍后重试。",
    }


def test_get_session_returns_session_snapshot(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sessions/sess_123",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session_id"] == "sess_123"
    assert body["data"]["role"] == "barista"
    assert body["data"]["visual_anchors"] == ["counter", "menu board"]
    assert body["data"]["vocab_candidates"] == ["coffee", "order"]
    assert body["data"]["messages"][0]["text"] == "Hi there, what can I get started for you today?"


def test_reply_to_session_returns_updated_messages_and_feedback(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions/sess_123/reply",
        json={"learner_message": "Could I get an iced latte, please?"},
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session"]["session_id"] == "sess_123"
    assert len(body["data"]["session"]["messages"]) == 3
    assert body["data"]["feedback"] == {
        "grammar": "Your meaning is clear.",
        "more_natural": "Could I get an iced latte, please?",
        "useful_words": ["latte", "size", "iced"],
    }


def test_reply_to_session_rejects_blank_message(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions/sess_123/reply",
        json={"learner_message": "   "},
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
    assert response.json()["message"] == "Validation error"


def test_get_session_review_returns_review_snapshot(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sessions/sess_123/review",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session_id"] == "sess_123"
    assert body["data"]["title"] == "本轮回响"
    assert body["data"]["feedback"]["grammar"]["title"] == "Grammar"
    assert body["data"]["feedback"]["useful_words"]["words"] == ["latte", "size", "iced"]


def test_bootstrap_voice_session_returns_deepgram_configuration(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions/sess_123/voice/bootstrap",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session_id"] == "sess_123"
    assert body["data"]["deepgram_access_token"] == "dg-token"
    assert body["data"]["deepgram_ws_url"] == "wss://api.deepgram.com/v1/agent/converse"
    assert body["data"]["agent_settings"]["type"] == "Settings"
    assert body["data"]["session"]["session_id"] == "sess_123"


def test_bootstrap_voice_session_returns_voice_token_error(client: TestClient) -> None:
    assert get_session_service is not None
    app.dependency_overrides[get_session_service] = lambda: VoiceBootstrapFailureSessionService()

    response = client.post(
        "/api/v1/sessions/sess_123/voice/bootstrap",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": 1302,
        "message": "Deepgram token 获取失败",
    }


def test_complete_voice_session_persists_transcript_and_returns_review(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions/sess_123/voice/complete",
        json={
            "conversation": [
                {"role": "assistant", "content": "Hi there, what can I get started for you today?"},
                {"role": "user", "content": "Could I get an iced latte, please?"},
                {"role": "assistant", "content": "Of course. What size would you like?"},
            ],
            "termination_reason": "user_ended",
        },
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session"]["session_id"] == "sess_123"
    assert [message["text"] for message in body["data"]["session"]["messages"]] == [
        "Hi there, what can I get started for you today?",
        "Could I get an iced latte, please?",
        "Of course. What size would you like?",
    ]
    assert body["data"]["review"]["title"] == "本轮回响"


def test_complete_voice_session_rejects_empty_conversation_payload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions/sess_123/voice/complete",
        json={
            "conversation": [],
            "termination_reason": "user_ended",
        },
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
    assert response.json()["message"] == "Validation error"


def test_complete_voice_session_rejects_payload_without_user_turn(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions/sess_123/voice/complete",
        json={
            "conversation": [
                {"role": "assistant", "content": "Hi there, what can I get started for you today?"}
            ],
            "termination_reason": "user_ended",
        },
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
    assert response.json()["message"] == "Validation error"


def test_list_history_sessions_returns_paginated_history_entries(client: TestClient) -> None:
    response = client.get(
        "/api/v1/history/sessions?limit=1",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert len(body["data"]["items"]) == 1
    assert body["data"]["items"][0]["id"] == "sess_456"
    assert body["data"]["page"]["has_more"] is True
    assert body["data"]["page"]["next_cursor"] is not None

    next_cursor = body["data"]["page"]["next_cursor"]
    second_response = client.get(
        f"/api/v1/history/sessions?limit=1&cursor={next_cursor}",
        headers={"Authorization": "Bearer valid-access-token"},
    )
    second_body = second_response.json()
    assert second_response.status_code == 200
    assert [entry["id"] for entry in second_body["data"]["items"]] == ["sess_123"]
    assert second_body["data"]["items"][0]["scene_title"] == "咖啡店柜台点单"
    assert second_body["data"]["items"][0]["vocab_candidates"] == ["coffee", "order"]
    assert second_body["data"]["items"][0]["review_title"] == "本轮回响"
    assert second_body["data"]["items"][0]["review_summary"] == "下一轮先说主需求，再补一条口味或杯型细节。"
    assert second_body["data"]["page"]["has_more"] is False


def test_get_history_session_returns_overview_and_review(client: TestClient) -> None:
    response = client.get(
        "/api/v1/history/sessions/sess_123",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["entry"]["id"] == "sess_123"
    assert body["data"]["entry"]["vocab_candidates"] == ["coffee", "order"]
    assert body["data"]["session"]["session_id"] == "sess_123"
    assert body["data"]["session"]["visual_anchors"] == ["counter", "menu board"]
    assert body["data"]["session"]["total_messages"] == 1
    assert body["data"]["review"]["title"] == "本轮回响"


def test_get_history_session_messages_returns_paginated_replay(client: TestClient) -> None:
    response = client.get(
        "/api/v1/history/sessions/sess_456/messages?limit=2",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert [item["message_id"] for item in body["data"]["items"]] == ["msg_11", "msg_12"]
    assert body["data"]["page"]["has_more"] is True
    assert body["data"]["page"]["next_cursor"] == "msg_11"

    second_response = client.get(
        "/api/v1/history/sessions/sess_456/messages?limit=2&cursor=msg_11",
        headers={"Authorization": "Bearer valid-access-token"},
    )
    second_body = second_response.json()
    assert second_response.status_code == 200
    assert [item["message_id"] for item in second_body["data"]["items"]] == ["msg_10"]
    assert second_body["data"]["page"]["has_more"] is False


def test_get_session_returns_not_found_error(client: TestClient) -> None:
    response = client.get(
        "/api/v1/sessions/sess_missing",
        headers={"Authorization": "Bearer valid-access-token"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": 1004,
        "message": "Session sess_missing not found",
    }


def test_reply_returns_429_envelope_when_rate_limit_exceeded(client: TestClient) -> None:
    limiter = InMemoryLLMRateLimiter(
        rules={"reply": LLMRateLimitRule(limit=1, window_seconds=3600)}
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    headers = {"Authorization": "Bearer valid-access-token"}
    first = client.post(
        "/api/v1/sessions/sess_123/reply",
        json={"learner_message": "Could I get an iced latte?"},
        headers=headers,
    )
    second = client.post(
        "/api/v1/sessions/sess_123/reply",
        json={"learner_message": "And a croissant, please."},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == 1006


def _visitor_cookie_value(response) -> str | None:
    """从响应 Set-Cookie 头解出访客 Cookie 值；未设置时返回 None。"""
    cookie_header = response.headers.get("set-cookie")
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(settings.auth_visitor_cookie_name)
    return morsel.value if morsel else None


def test_forged_visitor_cookie_is_rejected_and_reissued(client: TestClient) -> None:
    service = VisitorAwareSessionService()
    app.dependency_overrides[get_session_service] = lambda: service

    response = client.get(
        "/api/v1/sessions/sess_123",
        headers={"Cookie": f"{settings.auth_visitor_cookie_name}=visitor_forge"},
    )

    assert response.status_code == 200
    set_cookie_value = _visitor_cookie_value(response)
    # 伪造值被验签拒绝：响应用全新签名 Cookie 重新签发身份。
    assert set_cookie_value is not None
    assert set_cookie_value != "visitor_forge"
    visitor_id = verify_signed_value(set_cookie_value, secret=settings.auth_jwt_secret)
    assert visitor_id is not None
    assert visitor_id != "visitor_forge"
    # 伪造值没有进入 owner：本次请求走的是重新签发的访客身份。
    assert service.seen_owner_ids == [f"visitor:{visitor_id}"]


def test_forged_visitor_cookie_hits_missing_session_returns_404_without_500(
    client: TestClient,
) -> None:
    """伪造 Cookie 不许打崩请求：访问不存在的会话仍是标准 404 信封。"""
    app.dependency_overrides[get_session_service] = lambda: VisitorAwareSessionService()

    response = client.get(
        "/api/v1/sessions/sess_missing",
        headers={"Cookie": f"{settings.auth_visitor_cookie_name}=visitor_forge"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == 1004


def test_valid_signed_visitor_cookie_is_trusted_without_reset(client: TestClient) -> None:
    service = VisitorAwareSessionService()
    app.dependency_overrides[get_session_service] = lambda: service

    signed = sign_value("visitor_trusted", secret=settings.auth_jwt_secret)
    response = client.get(
        "/api/v1/sessions/sess_123",
        headers={"Cookie": f"{settings.auth_visitor_cookie_name}={signed}"},
    )

    assert response.status_code == 200
    # 验签通过：沿用既有访客身份，且不重设 Cookie。
    assert service.seen_owner_ids == ["visitor:visitor_trusted"]
    assert settings.auth_visitor_cookie_name not in response.headers.get("set-cookie", "")


def test_legacy_unsigned_visitor_cookie_is_reissued(client: TestClient) -> None:
    """旧版未签名 Cookie 一律视为无效：重新签发，不沿用旧值。"""
    service = VisitorAwareSessionService()
    app.dependency_overrides[get_session_service] = lambda: service

    response = client.get(
        "/api/v1/sessions/sess_123",
        headers={"Cookie": f"{settings.auth_visitor_cookie_name}=visitor_smoke_owner"},
    )

    assert response.status_code == 200
    set_cookie_value = _visitor_cookie_value(response)
    assert set_cookie_value is not None
    assert verify_signed_value(set_cookie_value, secret=settings.auth_jwt_secret) is not None
    assert service.seen_owner_ids != ["visitor:visitor_smoke_owner"]


def test_anonymous_rotating_cookies_hit_ip_rate_limit(client: TestClient) -> None:
    """同 IP 轮换 Cookie 刷新配额：visitor 键挡不住，IP 兜底键返回 429。"""
    app.dependency_overrides[get_session_service] = lambda: VisitorAwareSessionService()
    limiter = InMemoryLLMRateLimiter(
        rules={
            "session_start": LLMRateLimitRule(limit=100, window_seconds=3600),
            "session_start_ip": LLMRateLimitRule(limit=2, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    # TestClient 的对端地址固定为 testclient：每次请求换一个伪造 Cookie，
    # visitor 键始终是全新身份，第 3 次请求撞上 IP 限额（limit=2）。
    responses = [
        client.post(
            "/api/v1/sessions",
            json={"sample_scene_id": "coffee"},
            headers={"Cookie": f"{settings.auth_visitor_cookie_name}=forged_{index}"},
        )
        for index in range(3)
    ]

    assert [response.status_code for response in responses[:2]] == [200, 200]
    assert responses[2].status_code == 429
    assert responses[2].json()["code"] == 1006


def test_authenticated_user_bursts_do_not_consume_ip_quota(client: TestClient) -> None:
    """认证用户不受 IP 兜底键影响：IP 限额调到 1 也应连发无阻。"""
    limiter = InMemoryLLMRateLimiter(
        rules={
            "session_start": LLMRateLimitRule(limit=10, window_seconds=3600),
            "session_start_ip": LLMRateLimitRule(limit=1, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    headers = {"Authorization": "Bearer valid-access-token"}
    for _ in range(3):
        response = client.post("/api/v1/sessions", json={"media_id": "med_123"}, headers=headers)
        assert response.status_code == 200


def test_bootstrap_voice_session_rate_limited_before_token_issuance(client: TestClient) -> None:
    """owner 超限 429，且限流先于签发：超限请求零 Deepgram token grant。"""
    issuer = RecordingDeepgramTokenIssuer()
    app.dependency_overrides[get_session_service] = lambda: IssuerBackedVoiceSessionService(issuer)
    limiter = InMemoryLLMRateLimiter(
        rules={
            "voice_bootstrap": LLMRateLimitRule(limit=1, window_seconds=3600),
            "voice_bootstrap_ip": LLMRateLimitRule(limit=100, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    headers = {"Authorization": "Bearer valid-access-token"}
    first = client.post("/api/v1/sessions/sess_123/voice/bootstrap", headers=headers)
    second = client.post("/api/v1/sessions/sess_123/voice/bootstrap", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["code"] == 1006
    # fake issuer 签发次数 == 成功次数：被限流的第二次请求没有签发任何令牌。
    assert issuer.grant_calls == 1


def test_anonymous_rotating_cookies_hit_bootstrap_ip_rate_limit(client: TestClient) -> None:
    """匿名同 IP 轮换 Cookie：owner 键每次都是新访客挡不住，IP 兜底键 429。"""
    issuer = RecordingDeepgramTokenIssuer()
    app.dependency_overrides[get_session_service] = lambda: IssuerBackedVoiceSessionService(issuer)
    limiter = InMemoryLLMRateLimiter(
        rules={
            "voice_bootstrap": LLMRateLimitRule(limit=100, window_seconds=3600),
            "voice_bootstrap_ip": LLMRateLimitRule(limit=2, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    # TestClient 的对端地址固定为 testclient：每次请求换一个伪造 Cookie，
    # visitor 键始终是全新身份，第 3 次请求撞上 IP 限额（limit=2）。
    responses = [
        client.post(
            "/api/v1/sessions/sess_123/voice/bootstrap",
            headers={"Cookie": f"{settings.auth_visitor_cookie_name}=forged_{index}"},
        )
        for index in range(3)
    ]

    assert [response.status_code for response in responses[:2]] == [200, 200]
    assert responses[2].status_code == 429
    assert responses[2].json()["code"] == 1006
    assert issuer.grant_calls == 2


def test_authenticated_user_bootstrap_does_not_consume_ip_quota(client: TestClient) -> None:
    """认证用户 bootstrap 不受 IP 兜底键影响：IP 限额调到 1 也应连发无阻。"""
    app.dependency_overrides[get_session_service] = lambda: IssuerBackedVoiceSessionService(
        RecordingDeepgramTokenIssuer()
    )
    limiter = InMemoryLLMRateLimiter(
        rules={
            "voice_bootstrap": LLMRateLimitRule(limit=10, window_seconds=3600),
            "voice_bootstrap_ip": LLMRateLimitRule(limit=1, window_seconds=3600),
        }
    )
    app.dependency_overrides[get_llm_rate_limiter] = lambda: limiter

    headers = {"Authorization": "Bearer valid-access-token"}
    for _ in range(3):
        response = client.post("/api/v1/sessions/sess_123/voice/bootstrap", headers=headers)
        assert response.status_code == 200
