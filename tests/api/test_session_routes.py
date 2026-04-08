from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.common.exceptions import AuthenticationError
from api.common.exceptions import NotFoundError
from api.common.exceptions import SceneAnalysisUnavailableError
from api.common.exceptions import UnsupportedSceneImageError
from api.common.exceptions import VoiceTokenError
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

    def start_session(
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

    def get_session(self, session_id: str, owner_id: str | None = None) -> Session:
        assert owner_id in (None, "user:user_123")
        session = self.sessions.get(session_id)
        if session is None:
            raise NotFoundError(f"Session {session_id} not found")
        return session

    def reply_to_session(
        self,
        session_id: str,
        learner_message: str,
        owner_id: str | None = None,
    ) -> Session:
        assert owner_id in (None, "user:user_123")
        session = self.get_session(session_id)
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

    def get_session_review(self, session_id: str, owner_id: str | None = None):
        assert owner_id in (None, "user:user_123")
        review = self.reviews.get(session_id)
        if review is None:
            raise NotFoundError(f"Session review {session_id} not found")
        return review

    def list_history_sessions(self, user_id: str) -> list[Session]:
        assert user_id == "user:user_123"
        return list(self.sessions.values())

    def list_history_sessions_page(
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

    def list_history_reviews(self, session_ids: list[str]):
        return {
            session_id: review
            for session_id, review in self.reviews.items()
            if session_id in session_ids
        }

    def get_history_session_overview(self, user_id: str, session_id: str):
        assert user_id == "user:user_123"
        session = self.get_session(session_id)
        review = self.get_session_review(session_id)
        return (session, review, len(session.messages))

    def list_history_session_messages(
        self,
        user_id: str,
        session_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Message], bool, str | None]:
        assert user_id == "user:user_123"
        session = self.get_session(session_id)
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

    def get_history_session_detail(self, user_id: str, session_id: str):
        assert user_id == "user:user_123"
        session = self.get_session(session_id)
        review = self.get_session_review(session_id)
        return (session, review)

    def bootstrap_voice_session(self, session_id: str, owner_id: str | None = None):
        assert owner_id in (None, "user:user_123")
        session = self.get_session(session_id)
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

    def complete_voice_session(
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
        session = self.get_session(session_id)
        session.messages = [
            Message(id="msg_1", role="assistant", text="Hi there, what can I get started for you today?"),
            Message(id="msg_2", role="user", text="Could I get an iced latte, please?"),
            Message(id="msg_3", role="assistant", text="Of course. What size would you like?"),
        ]
        self.sessions[session_id] = session
        review = self.get_session_review("sess_123")
        self.reviews[session_id] = review
        return {"session": session, "review": review}


class FakeAuthService:
    def get_current_user(self, *, access_token: str) -> User:
        if access_token != "valid-access-token":
            raise AuthenticationError("Authentication required")
        return User(id="user_123", email="learner@example.com", nickname="Echo Learner")


class UnsupportedSessionService:
    def start_session(
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
    def start_session(
        self,
        user_id: str,
        media_id: str | None = None,
        sample_scene_id: str | None = None,
    ) -> Session:
        raise SceneAnalysisUnavailableError()


class VoiceBootstrapFailureSessionService(FakeSessionService):
    def bootstrap_voice_session(self, session_id: str, owner_id: str | None = None):
        raise VoiceTokenError()


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
