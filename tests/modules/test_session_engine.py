from __future__ import annotations

import asyncio

import pytest

from api.common.enums import MediaUploadStatus
from api.common.exceptions import EchoWhaleError
from api.common.exceptions import NotFoundError
from api.common.exceptions import SceneAnalysisUnavailableError
from api.common.exceptions import UnsupportedSceneImageError
from api.common.exceptions import ValidationError as AppValidationError
from api.models.media_model import Media
from api.models.message_model import Message
from api.models.runtime_model import SessionEvent
from api.models.session_model import Session
from api.models.runtime_model import VoiceSessionFact
from api.modules.scene_engine.schema import SceneAnalysisResult
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.schema import ReplyInput, StartSessionInput
from api.modules.session_engine.schema import VoiceCompleteInput, VoiceConversationTurn
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

    async def save_reply_turn(self, session_id: str, learner_message: Message, assistant_message: Message, review) -> Session:
        session = self.sessions[session_id]
        session.messages.extend([learner_message, assistant_message])
        self.sessions[session_id] = session
        self.reviews[session_id] = review
        return session

    async def finalize_voice_session(
        self,
        *,
        session: Session,
        review,
        voice_fact: VoiceSessionFact,
        events: list[SessionEvent],
    ) -> tuple[Session, object]:
        self.sessions[session.id] = session
        self.reviews[review.session_id] = review
        self.voice_facts[voice_fact.session_id] = voice_fact
        self.events.setdefault(session.id, []).extend(events)
        return (session, review)

    async def save_session_review(self, review) -> object:
        self.reviews[review.session_id] = review
        return review

    async def get_session_review(self, session_id: str):
        return self.reviews[session_id]

    async def list_user_sessions(self, user_id: str) -> list[Session]:
        return [session for session in self.sessions.values() if session.user_id == user_id]

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

    async def count_session_messages(self, session_id: str) -> int:
        return len(self.sessions[session_id].messages)

    async def list_session_reviews_by_ids(self, session_ids: list[str]):
        return {session_id: self.reviews[session_id] for session_id in session_ids if session_id in self.reviews}


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

    async def async_create_signed_read_url(self, key: str, *, expires_in: int) -> tuple[str, object]:
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


def test_start_session_from_sample_preset_bypasses_media_lookup_and_scene_engine(
    fake_session_repository: FakeSessionRepository,
) -> None:
    agent = SessionEngineAgent(
        media_lookup=ExplodingMediaLookup(),
        session_repository=fake_session_repository,
    )
    agent.scene_engine = ExplodingSceneEngine()

    session = asyncio.run(agent.start(StartSessionInput(user_id="demo-user", sample_scene_id="coffee")))

    assert session.user_id == "demo-user"
    assert session.media_id is None
    assert session.scene == "coffee_shop"
    assert session.role
    assert session.vocab_candidates
    assert [message.text for message in session.messages] == [session.opener]
    assert asyncio.run(fake_session_repository.get_session(session.id)).scene == "coffee_shop"


class FailingCoachEngine:
    async def respond(self, scene: str, role: str, learner_message: str):
        raise RuntimeError("coach provider unavailable")


class FakeFeedbackEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[str]]] = []

    async def review(self, learner_message: str, scene: str, vocab_candidates: list[str]):
        from api.modules.feedback_engine.schema import FeedbackResult

        self.calls.append((learner_message, scene, vocab_candidates))

        return FeedbackResult(
            grammar="Your meaning is clear.",
            more_natural="Could I get an iced latte, please?",
            useful_words=vocab_candidates or ["latte", "size", "iced"],
        )


class FailingFeedbackEngine:
    async def review(self, learner_message: str, scene: str, vocab_candidates: list[str]):
        raise RuntimeError("feedback provider unavailable")


class RecordingCoachEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, list[str], list[str], list[Message]]] = []

    async def respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
    ):
        self.calls.append(
            (
                scene,
                role,
                learner_message,
                visual_anchors,
                vocab_candidates,
                recent_messages,
            )
        )
        from api.modules.coach_engine.schema import CoachReplyResult

        return CoachReplyResult(text=f"Let's keep practicing with {visual_anchors[0]}.")


class ConcurrentFeedbackEngine:
    def __init__(self, started: list[str], released: asyncio.Event) -> None:
        self.started = started
        self.released = released

    async def review(self, learner_message: str, scene: str, vocab_candidates: list[str]):
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

    def build(self, session: Session) -> dict[str, object]:
        self.calls.append(session)
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
        asyncio.run(agent.reply(ReplyInput(session_id="sess_123", learner_message="Could I get an iced latte, please?")))

    stored = asyncio.run(fake_session_repository.get_session("sess_123"))
    assert [message.id for message in stored.messages] == ["msg_1"]


def test_reply_passes_session_labels_and_recent_messages_to_downstream_engines(
    fake_session_repository: FakeSessionRepository,
) -> None:
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
        agent.reply(
            ReplyInput(session_id="sess_labels", learner_message="I would like a latte")
        )
    )

    assert feedback_engine.calls == [
        ("I would like a latte", "coffee_shop", ["latte", "menu"])
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
    }


def test_reply_runs_feedback_and_coach_generation_concurrently(
    fake_session_repository: FakeSessionRepository,
) -> None:
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
    saved_voice_fact = asyncio.run(fake_session_repository.get_latest_voice_session_fact("sess_voice"))
    assert saved_voice_fact is not None
    assert saved_voice_fact.status == "active"
    assert saved_voice_fact.termination_reason is None
    assert saved_voice_fact.transcript_turn_count == 1


def test_complete_voice_session_persists_transcript_and_generates_review(
    fake_session_repository: FakeSessionRepository,
) -> None:
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
                    VoiceConversationTurn(role="assistant", content="Hi there, what can I get started for you today?"),
                    VoiceConversationTurn(role="user", content="Could I get an iced latte, please?"),
                    VoiceConversationTurn(role="assistant", content="Of course. What size would you like?"),
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
    assert fake_session_repository.reviews["sess_voice_complete"].feedback.grammar.body == "Your meaning is clear."
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


def test_complete_voice_session_does_not_persist_transcript_when_feedback_generation_fails(
    fake_session_repository: FakeSessionRepository,
) -> None:
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

    with pytest.raises(RuntimeError, match="feedback provider unavailable"):
        asyncio.run(
            agent.complete_voice_session(
                VoiceCompleteInput(
                    session_id="sess_voice_feedback_fail",
                    conversation=[
                        VoiceConversationTurn(role="assistant", content="Hi there, what can I get started for you today?"),
                        VoiceConversationTurn(role="user", content="Could I get an iced latte, please?"),
                    ],
                    termination_reason="user_ended",
                )
            )
        )

    stored = asyncio.run(fake_session_repository.get_session("sess_voice_feedback_fail"))
    assert [message.text for message in stored.messages] == [
        "Hi there, what can I get started for you today?"
    ]
    assert fake_session_repository.reviews == {}
    assert asyncio.run(fake_session_repository.list_session_events("sess_voice_feedback_fail")) == []
    assert asyncio.run(fake_session_repository.get_latest_voice_session_fact("sess_voice_feedback_fail")) is None


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
