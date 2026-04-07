from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.db.database import create_all_tables, create_database_engine, create_session_factory
from api.db.session_db import SqlAlchemySessionRepository
from api.models.message_model import Message
from api.models.session_model import Session

try:
    from api.models.review_model import (
        FeedbackMetric,
        PracticeFeedback,
        SessionReview,
        UsefulWordsMetric,
    )
except ImportError:  # pragma: no cover - expected during red phase
    FeedbackMetric = None
    PracticeFeedback = None
    SessionReview = None
    UsefulWordsMetric = None


def test_sqlalchemy_session_repository_persists_session_and_messages(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'session.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    session = Session(
        id="sess_123",
        user_id="demo-user",
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

    repository.save_session(session)

    loaded = repository.get_session("sess_123")
    updated = repository.add_message(
        "sess_123",
        Message(
            id="msg_2",
            role="user",
            text="Could I get an iced latte, please?",
        ),
    )

    assert loaded.id == session.id
    assert loaded.media_id == session.media_id
    assert loaded.visual_anchors == ["counter"]
    assert loaded.vocab_candidates == ["coffee"]
    assert loaded.labels == ["counter", "coffee"]
    assert [message.id for message in loaded.messages] == ["msg_1"]
    assert [message.text for message in updated.messages] == [
        "Hi there, what can I get started for you today?",
        "Could I get an iced latte, please?",
    ]
    assert [item.id for item in repository.list_user_sessions("demo-user")] == ["sess_123"]


def test_sqlalchemy_session_repository_persists_review_snapshots(tmp_path) -> None:
    assert SessionReview is not None
    assert PracticeFeedback is not None
    assert FeedbackMetric is not None
    assert UsefulWordsMetric is not None

    database_url = f"sqlite:///{tmp_path / 'session-review.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    session = Session(
        id="sess_123",
        user_id="demo-user",
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
    repository.save_session(session)

    review = SessionReview(
        session_id="sess_123",
        title="本轮回响",
        highlight="你已经说清楚主要需求。",
        next_try="下一轮再补一条细节。",
        feedback=PracticeFeedback(
            grammar=FeedbackMetric(title="Grammar", body="Your meaning is clear."),
            more_natural=FeedbackMetric(
                title="More Natural",
                body="Could I get an iced latte, please?",
            ),
            useful_words=UsefulWordsMetric(
                title="Useful Words",
                words=["latte", "size", "iced"],
                body="把这些词带进下一轮回答，会更自然。",
            ),
            next_step=FeedbackMetric(
                title="Next Step",
                body="下一轮试着在一句主回应后再补一句细节。",
            ),
        ),
    )

    repository.save_session_review(review)

    loaded = repository.get_session_review("sess_123")

    assert loaded.session_id == "sess_123"
    assert loaded.title == "本轮回响"
    assert loaded.feedback.useful_words.words == ["latte", "size", "iced"]


def test_sqlalchemy_session_repository_lists_latest_sessions_first(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'session-order.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    earlier = Session(
        id="sess_early",
        user_id="demo-user",
        media_id="med_early",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["coffee"],
        messages=[],
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    later = Session(
        id="sess_late",
        user_id="demo-user",
        media_id="med_late",
        scene="office",
        role="coworker",
        opener="How is the feature going?",
        visual_anchors=["glass wall"],
        vocab_candidates=["office"],
        messages=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    repository.save_session(earlier)
    repository.save_session(later)

    listed = repository.list_user_sessions("demo-user")

    assert [session.id for session in listed] == ["sess_late", "sess_early"]


def test_sqlalchemy_session_repository_backfills_vocab_candidates_from_legacy_labels(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'session-legacy.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    session = Session(
        id="sess_legacy",
        user_id="demo-user",
        media_id="med_legacy",
        scene="office",
        role="coworker",
        opener="Can we review the timeline?",
        labels=["meeting", "deadline"],
        messages=[],
    )

    repository.save_session(session)

    loaded = repository.get_session("sess_legacy")

    assert loaded.visual_anchors == []
    assert loaded.vocab_candidates == ["meeting", "deadline"]
    assert loaded.labels == ["meeting", "deadline"]
