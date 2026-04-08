from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.db.database import create_all_tables, create_database_engine, create_session_factory
from api.db.session_db import SqlAlchemySessionRepository
from api.models.message_model import Message
from api.models.runtime_model import SessionEvent
from api.models.session_model import Session
from api.models.runtime_model import VoiceSessionFact

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


def test_sqlalchemy_session_repository_persists_sample_sessions_without_media_id(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'session-sample.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    session = Session(
        id="sess_sample",
        user_id="demo-user",
        media_id=None,
        scene="coffee_shop",
        role="friendly barista",
        opener="Hello! What would you like to order today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[
            Message(
                id="msg_sample_1",
                role="assistant",
                text="Hello! What would you like to order today?",
            )
        ],
    )

    repository.save_session(session)

    loaded = repository.get_session("sess_sample")

    assert loaded.media_id is None
    assert loaded.scene == "coffee_shop"
    assert loaded.messages[0].text == "Hello! What would you like to order today?"


def test_sqlalchemy_session_repository_persists_session_events_and_voice_facts(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'session-runtime.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    session = Session(
        id="sess_voice_runtime",
        user_id="demo-user",
        media_id="med_voice",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[
            Message(
                id="msg_voice_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    repository.save_session(session)

    repository.save_session_event(
        SessionEvent(
            session_id="sess_voice_runtime",
            event_type="voice_bootstrapped",
            stage="voice_active",
            payload={"expires_in": 600.0, "output_sample_rate": 24000},
        )
    )
    repository.save_voice_session_fact(
        VoiceSessionFact(
            session_id="sess_voice_runtime",
            status="completed",
            termination_reason="user_ended",
            transcript_turn_count=3,
            client_diagnostics={
                "processor_buffer_size": 2048,
                "track_sample_rate": 48000,
                "playback_gap_resets": 1,
            },
        )
    )

    loaded_events = repository.list_session_events("sess_voice_runtime")
    loaded_voice_fact = repository.get_latest_voice_session_fact("sess_voice_runtime")

    assert [event.event_type for event in loaded_events] == ["voice_bootstrapped"]
    assert loaded_events[0].stage == "voice_active"
    assert loaded_events[0].payload == {
        "expires_in": 600.0,
        "output_sample_rate": 24000,
    }
    assert loaded_voice_fact is not None
    assert loaded_voice_fact.session_id == "sess_voice_runtime"
    assert loaded_voice_fact.status == "completed"
    assert loaded_voice_fact.termination_reason == "user_ended"
    assert loaded_voice_fact.transcript_turn_count == 3
    assert loaded_voice_fact.client_diagnostics == {
        "processor_buffer_size": 2048,
        "track_sample_rate": 48000,
        "playback_gap_resets": 1,
    }


def test_sqlalchemy_session_repository_finalizes_voice_session_atomically(tmp_path) -> None:
    assert SessionReview is not None
    assert PracticeFeedback is not None
    assert FeedbackMetric is not None
    assert UsefulWordsMetric is not None

    database_url = f"sqlite:///{tmp_path / 'session-voice-finalize.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    original = Session(
        id="sess_voice_finalized",
        user_id="demo-user",
        media_id="med_voice",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )
    repository.save_session(original)

    finalized_session = original.model_copy(
        update={
            "messages": [
                *original.messages,
                Message(id="msg_2", role="user", text="Could I get an iced latte, please?"),
                Message(id="msg_3", role="assistant", text="Of course. What size would you like?"),
            ]
        }
    )
    review = SessionReview(
        session_id="sess_voice_finalized",
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
    voice_fact = VoiceSessionFact(
        session_id="sess_voice_finalized",
        status="completed",
        termination_reason="user_ended",
        transcript_turn_count=3,
        client_diagnostics={"playback_gap_resets": 1},
        completed_at=review.updated_at,
        updated_at=review.updated_at,
    )
    events = [
        SessionEvent(
            session_id="sess_voice_finalized",
            event_type="voice_finalized",
            stage="review_ready",
            payload={"termination_reason": "user_ended", "conversation_turn_count": 3},
            created_at=review.updated_at,
        ),
        SessionEvent(
            session_id="sess_voice_finalized",
            event_type="review_built",
            stage="review_ready",
            payload={"review_title": review.title},
            created_at=review.updated_at,
        ),
    ]

    repository.finalize_voice_session(
        session=finalized_session,
        review=review,
        voice_fact=voice_fact,
        events=events,
    )

    loaded_session = repository.get_session("sess_voice_finalized")
    loaded_review = repository.get_session_review("sess_voice_finalized")
    loaded_events = repository.list_session_events("sess_voice_finalized")
    loaded_voice_fact = repository.get_latest_voice_session_fact("sess_voice_finalized")

    assert [message.id for message in loaded_session.messages] == ["msg_1", "msg_2", "msg_3"]
    assert loaded_review.title == "本轮回响"
    assert [event.event_type for event in loaded_events] == ["voice_finalized", "review_built"]
    assert loaded_voice_fact is not None
    assert loaded_voice_fact.status == "completed"


def test_sqlalchemy_session_repository_lists_history_page_and_reviews_in_batch(tmp_path) -> None:
    assert SessionReview is not None
    assert PracticeFeedback is not None
    assert FeedbackMetric is not None
    assert UsefulWordsMetric is not None

    database_url = f"sqlite:///{tmp_path / 'session-history-page.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    base = datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc)
    sessions = [
        Session(
            id="sess_a",
            user_id="demo-user",
            media_id="med_a",
            scene="coffee_shop",
            role="barista",
            opener="A",
            visual_anchors=["counter"],
            vocab_candidates=["coffee"],
            messages=[Message(id="msg_a1", role="assistant", text="A1")],
            created_at=base,
            updated_at=base,
        ),
        Session(
            id="sess_b",
            user_id="demo-user",
            media_id="med_b",
            scene="office",
            role="teammate",
            opener="B",
            visual_anchors=["meeting"],
            vocab_candidates=["update"],
            messages=[Message(id="msg_b1", role="assistant", text="B1")],
            created_at=base + timedelta(minutes=1),
            updated_at=base + timedelta(minutes=1),
        ),
        Session(
            id="sess_c",
            user_id="demo-user",
            media_id="med_c",
            scene="travel",
            role="guide",
            opener="C",
            visual_anchors=["street"],
            vocab_candidates=["direction"],
            messages=[Message(id="msg_c1", role="assistant", text="C1")],
            created_at=base + timedelta(minutes=2),
            updated_at=base + timedelta(minutes=2),
        ),
    ]
    for session in sessions:
        repository.save_session(session)
        repository.save_session_review(
            SessionReview(
                session_id=session.id,
                title=f"Review {session.id}",
                highlight=f"Highlight {session.id}",
                next_try=f"Next {session.id}",
                feedback=PracticeFeedback(
                    grammar=FeedbackMetric(title="Grammar", body="ok"),
                    more_natural=FeedbackMetric(title="More Natural", body="ok"),
                    useful_words=UsefulWordsMetric(title="Useful Words", words=["one"], body="ok"),
                    next_step=FeedbackMetric(title="Next Step", body="ok"),
                ),
            )
        )

    first_page, has_more, next_cursor = repository.list_user_sessions_page(
        "demo-user",
        limit=2,
        cursor=None,
    )

    assert [session.id for session in first_page] == ["sess_c", "sess_b"]
    assert has_more is True
    assert next_cursor is not None
    assert all(session.messages == [] for session in first_page)

    second_page, second_has_more, _ = repository.list_user_sessions_page(
        "demo-user",
        limit=2,
        cursor=next_cursor,
    )
    assert [session.id for session in second_page] == ["sess_a"]
    assert second_has_more is False

    reviews = repository.list_session_reviews_by_ids(["sess_c", "sess_a", "sess_missing"])
    assert set(reviews.keys()) == {"sess_c", "sess_a"}
    assert reviews["sess_c"].title == "Review sess_c"
    assert reviews["sess_a"].highlight == "Highlight sess_a"


def test_sqlalchemy_session_repository_lists_replay_messages_page(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'session-replay-page.db'}"
    engine = create_database_engine(database_url)
    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    session = Session(
        id="sess_replay",
        user_id="demo-user",
        media_id="med_replay",
        scene="coffee_shop",
        role="barista",
        opener="Hi",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[
            Message(id="msg_1", role="assistant", text="Hi there"),
            Message(id="msg_2", role="user", text="Could I get an iced latte?"),
            Message(id="msg_3", role="assistant", text="Sure, what size?"),
            Message(id="msg_4", role="user", text="Medium, please."),
            Message(id="msg_5", role="assistant", text="Great choice."),
        ],
    )
    repository.save_session(session)

    items, has_more, next_cursor = repository.list_session_messages_page(
        "sess_replay",
        limit=2,
        cursor=None,
    )
    assert [message.id for message in items] == ["msg_4", "msg_5"]
    assert has_more is True
    assert next_cursor is not None
    assert repository.count_session_messages("sess_replay") == 5

    previous_items, previous_has_more, _ = repository.list_session_messages_page(
        "sess_replay",
        limit=3,
        cursor=next_cursor,
    )
    assert [message.id for message in previous_items] == ["msg_1", "msg_2", "msg_3"]
    assert previous_has_more is False
