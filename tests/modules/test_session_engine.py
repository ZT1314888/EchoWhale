from __future__ import annotations

import pytest

from api.common.enums import MediaUploadStatus
from api.common.exceptions import EchoWhaleError
from api.models.media_model import Media
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.scene_engine.schema import SceneAnalysisResult
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.schema import ReplyInput, StartSessionInput
from api.modules.session_engine.service import SessionEngineService


class FakeMediaLookup:
    def __init__(self, media: Media) -> None:
        self.media = media

    def get_media(self, media_id: str) -> Media:
        assert media_id == self.media.id
        return self.media


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.reviews: dict[str, object] = {}

    def save_session(self, session: Session) -> Session:
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session:
        return self.sessions[session_id]

    def add_message(self, session_id: str, message: Message) -> Session:
        session = self.sessions[session_id]
        session.messages.append(message)
        self.sessions[session_id] = session
        return session

    def save_reply_turn(self, session_id: str, learner_message: Message, assistant_message: Message, review) -> Session:
        session = self.sessions[session_id]
        session.messages.extend([learner_message, assistant_message])
        self.sessions[session_id] = session
        self.reviews[session_id] = review
        return session

    def save_session_review(self, review) -> object:
        self.reviews[review.session_id] = review
        return review

    def get_session_review(self, session_id: str):
        return self.reviews[session_id]

    def list_user_sessions(self, user_id: str) -> list[Session]:
        return [session for session in self.sessions.values() if session.user_id == user_id]


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
        service.start_session(user_id="demo-user", media_id="med_pending")


class FakeReadUrlSigner:
    def __init__(self) -> None:
        self.requested_keys: list[str] = []

    def create_signed_read_url(self, key: str, *, expires_in: int) -> tuple[str, object]:
        self.requested_keys.append(key)
        return ("https://signed.test/media/demo-user/coffee-shop.png", object())


class FakeSceneEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def analyze(self, filename: str, media_url: str) -> SceneAnalysisResult:
        self.calls.append((filename, media_url))
        return SceneAnalysisResult(
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            labels=["coffee"],
            confidence=0.83,
        )


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

    session = agent.start(StartSessionInput(user_id="demo-user", media_id=media.id))

    assert session.media_id == media.id
    assert session.user_id == "demo-user"
    assert signer.requested_keys == [media.storage_key]
    assert scene_engine.calls == [
        ("coffee-shop.png", "https://signed.test/media/demo-user/coffee-shop.png")
    ]


class FailingCoachEngine:
    def respond(self, scene: str, role: str, learner_message: str):
        raise RuntimeError("coach provider unavailable")


class FakeFeedbackEngine:
    def review(self, learner_message: str, scene: str):
        from api.modules.feedback_engine.schema import FeedbackResult

        return FeedbackResult(
            grammar="Your meaning is clear.",
            more_natural="Could I get an iced latte, please?",
            useful_words=["latte", "size", "iced"],
        )


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
        labels=["coffee"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    fake_session_repository.save_session(session)
    agent = SessionEngineAgent(session_repository=fake_session_repository)
    agent.feedback_engine = FakeFeedbackEngine()
    agent.coach_engine = FailingCoachEngine()

    with pytest.raises(RuntimeError, match="coach provider unavailable"):
        agent.reply(ReplyInput(session_id="sess_123", learner_message="Could I get an iced latte, please?"))

    stored = fake_session_repository.get_session("sess_123")
    assert [message.id for message in stored.messages] == ["msg_1"]
