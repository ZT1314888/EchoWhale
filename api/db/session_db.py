from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from api.common.enums import SessionStatus
from api.common.exceptions import NotFoundError
from api.db.database import Base, SessionFactory, get_session_factory
from api.models.message_model import Message
from api.models.review_model import PracticeFeedback, SessionReview
from api.models.session_model import Session


class SessionRepository(Protocol):
    def save_session(self, session: Session) -> Session: ...

    def get_session(self, session_id: str) -> Session: ...

    def add_message(self, session_id: str, message: Message) -> Session: ...

    def save_reply_turn(
        self,
        session_id: str,
        learner_message: Message,
        assistant_message: Message,
        review: SessionReview,
    ) -> Session: ...

    def save_session_review(self, review: SessionReview) -> SessionReview: ...

    def get_session_review(self, session_id: str) -> SessionReview: ...

    def list_user_sessions(self, user_id: str) -> list[Session]: ...


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    media_id: Mapped[str] = mapped_column(String(64), index=True)
    scene: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(128))
    opener: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    visual_anchors: Mapped[list[str]] = mapped_column(JSON, default=list)
    vocab_candidates: Mapped[list[str]] = mapped_column(JSON, default=list)
    labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MessageRecord(Base):
    __tablename__ = "session_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    feedback: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionReviewRecord(Base):
    __tablename__ = "session_reviews"

    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    title: Mapped[str] = mapped_column(String(128))
    highlight: Mapped[str] = mapped_column(Text)
    next_try: Mapped[str] = mapped_column(Text)
    feedback: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SqlAlchemySessionRepository:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def save_session(self, session: Session) -> Session:
        with self._session_factory() as db_session:
            self._upsert_session_record(db_session, session)
            # 强制先落父 session，避免在 FK 严格数据库中先写子 message。
            db_session.flush()
            db_session.execute(
                delete(MessageRecord).where(MessageRecord.session_id == session.id)
            )
            for position, message in enumerate(session.messages):
                db_session.add(self._to_message_record(session.id, position, message))
            db_session.commit()
        return self.get_session(session.id)

    def get_session(self, session_id: str) -> Session:
        with self._session_factory() as db_session:
            record = db_session.get(SessionRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session {session_id} not found")
            messages = self._load_messages(db_session, session_id)
            return _to_session(record, messages)

    def add_message(self, session_id: str, message: Message) -> Session:
        with self._session_factory() as db_session:
            record = db_session.get(SessionRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session {session_id} not found")

            current_position = db_session.scalar(
                select(func.coalesce(func.max(MessageRecord.position), -1)).where(
                    MessageRecord.session_id == session_id
                )
            )
            db_session.add(
                self._to_message_record(
                    session_id,
                    int(current_position) + 1,
                    message,
                )
            )
            record.updated_at = message.created_at
            db_session.commit()
        return self.get_session(session_id)

    def save_reply_turn(
        self,
        session_id: str,
        learner_message: Message,
        assistant_message: Message,
        review: SessionReview,
    ) -> Session:
        with self._session_factory() as db_session:
            record = db_session.get(SessionRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session {session_id} not found")

            current_position = db_session.scalar(
                select(func.coalesce(func.max(MessageRecord.position), -1)).where(
                    MessageRecord.session_id == session_id
                )
            )
            next_position = int(current_position) + 1
            db_session.add(self._to_message_record(session_id, next_position, learner_message))
            db_session.add(
                self._to_message_record(session_id, next_position + 1, assistant_message)
            )
            self._upsert_review_record(db_session, review)
            record.updated_at = review.updated_at
            db_session.commit()
        return self.get_session(session_id)

    def save_session_review(self, review: SessionReview) -> SessionReview:
        with self._session_factory() as db_session:
            record = db_session.get(SessionRecord, review.session_id)
            if record is None:
                raise NotFoundError(f"Session {review.session_id} not found")
            self._upsert_review_record(db_session, review)
            record.updated_at = review.updated_at
            db_session.commit()
        return self.get_session_review(review.session_id)

    def get_session_review(self, session_id: str) -> SessionReview:
        with self._session_factory() as db_session:
            record = db_session.get(SessionReviewRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session review {session_id} not found")
            return _to_review(record)

    def list_user_sessions(self, user_id: str) -> list[Session]:
        with self._session_factory() as db_session:
            records = db_session.scalars(
                select(SessionRecord)
                .where(SessionRecord.user_id == user_id)
                .order_by(SessionRecord.updated_at.desc(), SessionRecord.id.desc())
            ).all()
            return [
                _to_session(record, self._load_messages(db_session, record.id))
                for record in records
            ]

    def reset(self) -> None:
        with self._session_factory() as db_session:
            db_session.execute(delete(SessionReviewRecord))
            db_session.execute(delete(MessageRecord))
            db_session.execute(delete(SessionRecord))
            db_session.commit()

    def _load_messages(self, db_session, session_id: str) -> Sequence[MessageRecord]:
        return db_session.scalars(
            select(MessageRecord)
            .where(MessageRecord.session_id == session_id)
            .order_by(MessageRecord.position.asc())
        ).all()

    def _upsert_session_record(self, db_session, session: Session) -> SessionRecord:
        record = db_session.get(SessionRecord, session.id)
        if record is None:
            record = SessionRecord(
                id=session.id,
                user_id=session.user_id,
                media_id=session.media_id,
                scene=session.scene,
                role=session.role,
                opener=session.opener,
                status=session.status.value,
                visual_anchors=list(session.visual_anchors),
                vocab_candidates=list(session.vocab_candidates),
                labels=list(session.labels),
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            db_session.add(record)
            return record

        record.user_id = session.user_id
        record.media_id = session.media_id
        record.scene = session.scene
        record.role = session.role
        record.opener = session.opener
        record.status = session.status.value
        record.visual_anchors = list(session.visual_anchors)
        record.vocab_candidates = list(session.vocab_candidates)
        record.labels = list(session.labels)
        record.created_at = session.created_at
        record.updated_at = session.updated_at
        return record

    def _upsert_review_record(self, db_session, review: SessionReview) -> None:
        record = db_session.get(SessionReviewRecord, review.session_id)
        if record is None:
            db_session.add(
                SessionReviewRecord(
                    session_id=review.session_id,
                    title=review.title,
                    highlight=review.highlight,
                    next_try=review.next_try,
                    feedback=review.feedback.model_dump(),
                    created_at=review.created_at,
                    updated_at=review.updated_at,
                )
            )
            return

        record.title = review.title
        record.highlight = review.highlight
        record.next_try = review.next_try
        record.feedback = review.feedback.model_dump()
        record.updated_at = review.updated_at

    def _to_message_record(
        self,
        session_id: str,
        position: int,
        message: Message,
    ) -> MessageRecord:
        return MessageRecord(
            id=message.id,
            session_id=session_id,
            position=position,
            role=message.role,
            text=message.text,
            feedback=message.feedback,
            created_at=message.created_at,
        )


def save_session(session: Session) -> Session:
    return SqlAlchemySessionRepository().save_session(session)


def get_session(session_id: str) -> Session:
    return SqlAlchemySessionRepository().get_session(session_id)


def add_message(session_id: str, message: Message) -> Session:
    return SqlAlchemySessionRepository().add_message(session_id, message)


def list_user_sessions(user_id: str) -> list[Session]:
    return SqlAlchemySessionRepository().list_user_sessions(user_id)


def reset_session_store() -> None:
    SqlAlchemySessionRepository().reset()


def build_session_repository(session_factory: SessionFactory | None = None) -> SessionRepository:
    return SqlAlchemySessionRepository(session_factory)


def _to_session(record: SessionRecord, messages: Sequence[MessageRecord]) -> Session:
    visual_anchors = list(getattr(record, "visual_anchors", []) or [])
    vocab_candidates = list(getattr(record, "vocab_candidates", []) or [])
    if not visual_anchors and not vocab_candidates and record.labels:
        vocab_candidates = list(record.labels or [])

    return Session(
        id=record.id,
        user_id=record.user_id,
        media_id=record.media_id,
        scene=record.scene,
        role=record.role,
        opener=record.opener,
        status=SessionStatus(record.status),
        visual_anchors=visual_anchors,
        vocab_candidates=vocab_candidates,
        labels=list(record.labels or []),
        messages=[
            Message(
                id=message.id,
                role=message.role,
                text=message.text,
                feedback=message.feedback,
                created_at=message.created_at,
            )
            for message in messages
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_review(record: SessionReviewRecord) -> SessionReview:
    return SessionReview(
        session_id=record.session_id,
        title=record.title,
        highlight=record.highlight,
        next_try=record.next_try,
        feedback=PracticeFeedback.model_validate(record.feedback),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
