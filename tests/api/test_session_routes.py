from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.common.exceptions import NotFoundError
from api.main import app
from api.models.message_model import Message
from api.models.session_model import Session

try:
    from api.routes.v1.sessions import get_session_service
except ImportError:  # pragma: no cover - expected during red phase
    get_session_service = None


class FakeSessionService:
    def __init__(self) -> None:
        self.sessions = {
            "sess_123": Session(
                id="sess_123",
                user_id="demo-user",
                media_id="med_123",
                scene="coffee_shop",
                role="barista",
                opener="Hi there, what can I get started for you today?",
                labels=["coffee", "menu"],
                messages=[
                    Message(
                        id="msg_1",
                        role="assistant",
                        text="Hi there, what can I get started for you today?",
                    )
                ],
            )
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
            )
        }

    def start_session(self, user_id: str, media_id: str) -> Session:
        assert user_id == "demo-user"
        session = Session(
            id="sess_created",
            user_id=user_id,
            media_id=media_id,
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            labels=["coffee", "menu"],
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

    def get_session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise NotFoundError(f"Session {session_id} not found")
        return session

    def reply_to_session(self, session_id: str, learner_message: str) -> Session:
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

    def get_session_review(self, session_id: str):
        review = self.reviews.get(session_id)
        if review is None:
            raise NotFoundError(f"Session review {session_id} not found")
        return review

    def list_history_sessions(self, user_id: str) -> list[Session]:
        assert user_id == "demo-user"
        return list(self.sessions.values())

    def get_history_session_detail(self, user_id: str, session_id: str):
        assert user_id == "demo-user"
        session = self.get_session(session_id)
        review = self.get_session_review(session_id)
        return (session, review)


@pytest.fixture(autouse=True)
def clear_session_overrides() -> Iterator[None]:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    if get_session_service is not None:
        app.dependency_overrides[get_session_service] = lambda: FakeSessionService()

    with TestClient(app) as test_client:
        yield test_client


def test_start_session_returns_created_session(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions",
        json={"media_id": "med_123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session_id"] == "sess_created"
    assert body["data"]["media_id"] == "med_123"
    assert body["data"]["scene"] == "coffee_shop"
    assert body["data"]["messages"][0]["message_id"] == "msg_created_1"


def test_get_session_returns_session_snapshot(client: TestClient) -> None:
    response = client.get("/api/v1/sessions/sess_123")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session_id"] == "sess_123"
    assert body["data"]["role"] == "barista"
    assert body["data"]["messages"][0]["text"] == "Hi there, what can I get started for you today?"


def test_reply_to_session_returns_updated_messages_and_feedback(client: TestClient) -> None:
    response = client.post(
        "/api/v1/sessions/sess_123/reply",
        json={"learner_message": "Could I get an iced latte, please?"},
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
    )

    assert response.status_code == 400
    assert response.json()["code"] == 1001
    assert response.json()["message"] == "Validation error"


def test_get_session_review_returns_review_snapshot(client: TestClient) -> None:
    response = client.get("/api/v1/sessions/sess_123/review")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["session_id"] == "sess_123"
    assert body["data"]["title"] == "本轮回响"
    assert body["data"]["feedback"]["grammar"]["title"] == "Grammar"
    assert body["data"]["feedback"]["useful_words"]["words"] == ["latte", "size", "iced"]


def test_list_history_sessions_returns_real_history_entries(client: TestClient) -> None:
    response = client.get("/api/v1/history/sessions")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == "sess_123"
    assert body["data"][0]["scene_title"] == "咖啡店柜台点单"
    assert body["data"][0]["review_title"] == "本轮回响"
    assert body["data"][0]["review_summary"] == "下一轮先说主需求，再补一条口味或杯型细节。"


def test_get_history_session_returns_session_and_review(client: TestClient) -> None:
    response = client.get("/api/v1/history/sessions/sess_123")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["entry"]["id"] == "sess_123"
    assert body["data"]["session"]["session_id"] == "sess_123"
    assert body["data"]["review"]["title"] == "本轮回响"


def test_get_session_returns_not_found_error(client: TestClient) -> None:
    response = client.get("/api/v1/sessions/sess_missing")

    assert response.status_code == 404
    assert response.json() == {
        "code": 1004,
        "message": "Session sess_missing not found",
    }
