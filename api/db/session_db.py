from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    and_,
    delete,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from api.common.enums import SessionStatus
from api.common.exceptions import NotFoundError
from api.db.database import Base, AsyncSessionFactory, get_async_session_factory
from api.models.message_model import Message
from api.models.runtime_model import SessionEvent
from api.models.runtime_model import VoiceSessionFact
from api.models.review_model import PracticeFeedback, SessionReview
from api.models.session_model import Session


class SessionRepository(Protocol):
    async def save_session(self, session: Session) -> Session: ...

    async def get_session(self, session_id: str) -> Session: ...

    async def add_message(self, session_id: str, message: Message) -> Session: ...

    async def save_reply_turn(
        self,
        session_id: str,
        learner_message: Message,
        assistant_message: Message,
        review: SessionReview,
    ) -> Session: ...

    async def finalize_voice_session(
        self,
        *,
        session: Session,
        review: SessionReview,
        voice_fact: VoiceSessionFact,
        events: list[SessionEvent],
    ) -> tuple[Session, SessionReview]: ...

    async def save_session_review(self, review: SessionReview) -> SessionReview: ...

    async def get_session_review(self, session_id: str) -> SessionReview: ...

    async def list_user_sessions(self, user_id: str) -> list[Session]: ...

    async def list_user_sessions_page(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: tuple[datetime, str] | None,
    ) -> tuple[list[Session], bool, tuple[datetime, str] | None]: ...

    async def list_session_reviews_by_ids(self, session_ids: list[str]) -> dict[str, SessionReview]: ...

    async def get_session_head(self, session_id: str) -> Session: ...

    async def count_session_messages(self, session_id: str) -> int: ...

    async def list_session_messages_page(
        self,
        session_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Message], bool, str | None]: ...

    async def save_session_event(self, event: SessionEvent) -> SessionEvent: ...

    async def list_session_events(self, session_id: str) -> list[SessionEvent]: ...

    async def save_voice_session_fact(self, fact: VoiceSessionFact) -> VoiceSessionFact: ...

    async def get_latest_voice_session_fact(self, session_id: str) -> VoiceSessionFact | None: ...


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    media_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
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


class SessionEventRecord(Base):
    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    stage: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class VoiceSessionFactRecord(Base):
    __tablename__ = "voice_session_facts"

    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    termination_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transcript_turn_count: Mapped[int] = mapped_column(Integer, default=0)
    client_diagnostics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SqlAlchemySessionRepository:
    def __init__(self, session_factory: AsyncSessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_async_session_factory()

    async def save_session(self, session: Session) -> Session:
        async with self._session_factory() as db_session:
            await self._upsert_session_record(db_session, session)
            # 强制先落父 session，避免在 FK 严格数据库中先写子 message。
            await db_session.flush()
            await db_session.execute(
                delete(MessageRecord).where(MessageRecord.session_id == session.id)
            )
            for position, message in enumerate(session.messages):
                db_session.add(await self._to_message_record(session.id, position, message))
            await db_session.commit()
        return await self.get_session(session.id)

    async def get_session(self, session_id: str) -> Session:
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session {session_id} not found")
            messages = await self._load_messages(db_session, session_id)
            return _to_session(record, messages)

    async def add_message(self, session_id: str, message: Message) -> Session:
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session {session_id} not found")

            current_position = await db_session.scalar(
                select(func.coalesce(func.max(MessageRecord.position), -1)).where(
                    MessageRecord.session_id == session_id
                )
            )
            db_session.add(
                await self._to_message_record(
                    session_id,
                    int(current_position) + 1,
                    message,
                )
            )
            record.updated_at = message.created_at
            await db_session.commit()
        return await self.get_session(session_id)

    async def save_reply_turn(
        self,
        session_id: str,
        learner_message: Message,
        assistant_message: Message,
        review: SessionReview,
    ) -> Session:
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session {session_id} not found")

            current_position = await db_session.scalar(
                select(func.coalesce(func.max(MessageRecord.position), -1)).where(
                    MessageRecord.session_id == session_id
                )
            )
            next_position = int(current_position) + 1
            db_session.add(await self._to_message_record(session_id, next_position, learner_message))
            db_session.add(
                await self._to_message_record(session_id, next_position + 1, assistant_message)
            )
            await self._upsert_review_record(db_session, review)
            record.updated_at = review.updated_at
            await db_session.commit()
        return await self.get_session(session_id)

    async def finalize_voice_session(
        self,
        *,
        session: Session,
        review: SessionReview,
        voice_fact: VoiceSessionFact,
        events: list[SessionEvent],
    ) -> tuple[Session, SessionReview]:
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionRecord, session.id)
            if record is None:
                raise NotFoundError(f"Session {session.id} not found")

            await self._upsert_session_record(db_session, session)
            await db_session.flush()
            await db_session.execute(
                delete(MessageRecord).where(MessageRecord.session_id == session.id)
            )
            for position, message in enumerate(session.messages):
                db_session.add(await self._to_message_record(session.id, position, message))

            await self._upsert_review_record(db_session, review)
            record.updated_at = review.updated_at
            await self._upsert_voice_session_fact_record(db_session, voice_fact)
            for event in events:
                db_session.add(
                    SessionEventRecord(
                        session_id=event.session_id,
                        event_type=event.event_type,
                        stage=event.stage,
                        payload=dict(event.payload),
                        created_at=event.created_at,
                    )
                )
            await db_session.commit()

        return (await self.get_session(session.id), await self.get_session_review(review.session_id))

    async def save_session_review(self, review: SessionReview) -> SessionReview:
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionRecord, review.session_id)
            if record is None:
                raise NotFoundError(f"Session {review.session_id} not found")
            await self._upsert_review_record(db_session, review)
            record.updated_at = review.updated_at
            await db_session.commit()
        return await self.get_session_review(review.session_id)

    async def get_session_review(self, session_id: str) -> SessionReview:
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionReviewRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session review {session_id} not found")
            return _to_review(record)

    async def list_user_sessions(self, user_id: str) -> list[Session]:
        async with self._session_factory() as db_session:
            records = await db_session.scalars(
                select(SessionRecord)
                .where(SessionRecord.user_id == user_id)
                .order_by(SessionRecord.updated_at.desc(), SessionRecord.id.desc())
            ).all()
            return [
                _to_session(record, await self._load_messages(db_session, record.id))
                for record in records
            ]

    async def list_user_sessions_page(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: tuple[datetime, str] | None,
    ) -> tuple[list[Session], bool, tuple[datetime, str] | None]:
        async with self._session_factory() as db_session:
            statement = (
                select(SessionRecord)
                .join(
                    SessionReviewRecord,
                    SessionReviewRecord.session_id == SessionRecord.id,
                )
                .where(SessionRecord.user_id == user_id)
            )
            if cursor is not None:
                cursor_time, cursor_id = cursor
                statement = statement.where(
                    or_(
                        SessionRecord.updated_at < cursor_time,
                        and_(
                            SessionRecord.updated_at == cursor_time,
                            SessionRecord.id < cursor_id,
                        ),
                    )
                )
            records = await db_session.scalars(
                statement
                .order_by(SessionRecord.updated_at.desc(), SessionRecord.id.desc())
                .limit(limit + 1)
            ).all()
            has_more = len(records) > limit
            page_records = records[:limit]
            next_cursor = None
            if has_more and page_records:
                last = page_records[-1]
                next_cursor = (last.updated_at, last.id)
            sessions = [_to_session_head(record) for record in page_records]
            return (sessions, has_more, next_cursor)

    async def list_session_reviews_by_ids(self, session_ids: list[str]) -> dict[str, SessionReview]:
        if not session_ids:
            return {}
        async with self._session_factory() as db_session:
            records = await db_session.scalars(
                select(SessionReviewRecord).where(SessionReviewRecord.session_id.in_(session_ids))
            ).all()
            return {record.session_id: _to_review(record) for record in records}

    async def get_session_head(self, session_id: str) -> Session:
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session {session_id} not found")
            return _to_session_head(record)

    async def count_session_messages(self, session_id: str) -> int:
        async with self._session_factory() as db_session:
            await self._ensure_session_exists(db_session, session_id)
            value = await db_session.scalar(
                select(func.count(MessageRecord.id)).where(MessageRecord.session_id == session_id)
            )
            return int(value or 0)

    async def list_session_messages_page(
        self,
        session_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Message], bool, str | None]:
        async with self._session_factory() as db_session:
            await self._ensure_session_exists(db_session, session_id)
            statement = select(MessageRecord).where(MessageRecord.session_id == session_id)
            if cursor is not None:
                cursor_position = await db_session.scalar(
                    select(MessageRecord.position).where(
                        MessageRecord.session_id == session_id,
                        MessageRecord.id == cursor,
                    )
                )
                if cursor_position is None:
                    raise NotFoundError(f"Message {cursor} not found")
                statement = statement.where(MessageRecord.position < int(cursor_position))

            records_desc = await db_session.scalars(
                statement.order_by(MessageRecord.position.desc()).limit(limit + 1)
            ).all()
            has_more = len(records_desc) > limit
            page_desc = records_desc[:limit]
            page = list(reversed(page_desc))
            next_cursor = page[0].id if has_more and page else None
            return ([self._to_message(item) for item in page], has_more, next_cursor)

    async def save_session_event(self, event: SessionEvent) -> SessionEvent:
        async with self._session_factory() as db_session:
            record = SessionEventRecord(
                session_id=event.session_id,
                event_type=event.event_type,
                stage=event.stage,
                payload=dict(event.payload),
                created_at=event.created_at,
            )
            db_session.add(record)
            await db_session.commit()
        return event

    async def list_session_events(self, session_id: str) -> list[SessionEvent]:
        async with self._session_factory() as db_session:
            records = await db_session.scalars(
                select(SessionEventRecord)
                .where(SessionEventRecord.session_id == session_id)
                .order_by(SessionEventRecord.id.asc())
            ).all()
            return [_to_session_event(record) for record in records]

    async def save_voice_session_fact(self, fact: VoiceSessionFact) -> VoiceSessionFact:
        async with self._session_factory() as db_session:
            await self._upsert_voice_session_fact_record(db_session, fact)
            await db_session.commit()
        loaded = await self.get_latest_voice_session_fact(fact.session_id)
        return loaded if loaded is not None else fact

    async def get_latest_voice_session_fact(self, session_id: str) -> VoiceSessionFact | None:
        async with self._session_factory() as db_session:
            record = await db_session.get(VoiceSessionFactRecord, session_id)
            if record is None:
                return None
            return _to_voice_session_fact(record)

    async def reset(self) -> None:
        async with self._session_factory() as db_session:
            await db_session.execute(delete(VoiceSessionFactRecord))
            await db_session.execute(delete(SessionEventRecord))
            await db_session.execute(delete(SessionReviewRecord))
            await db_session.execute(delete(MessageRecord))
            await db_session.execute(delete(SessionRecord))
            await db_session.commit()

    async def _load_messages(self, db_session, session_id: str) -> Sequence[MessageRecord]:
        return await db_session.scalars(
            select(MessageRecord)
            .where(MessageRecord.session_id == session_id)
            .order_by(MessageRecord.position.asc())
        ).all()

    async def _ensure_session_exists(self, db_session, session_id: str) -> None:
        record = await db_session.get(SessionRecord, session_id)
        if record is None:
            raise NotFoundError(f"Session {session_id} not found")

    def _to_message(self, message: MessageRecord) -> Message:
        return Message(
            id=message.id,
            role=message.role,
            text=message.text,
            feedback=message.feedback,
            created_at=message.created_at,
        )

    async def _upsert_session_record(self, db_session, session: Session) -> SessionRecord:
        record = await db_session.get(SessionRecord, session.id)
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

    async def _upsert_review_record(self, db_session, review: SessionReview) -> None:
        record = await db_session.get(SessionReviewRecord, review.session_id)
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

    async def _upsert_voice_session_fact_record(self, db_session, fact: VoiceSessionFact) -> None:
        record = await db_session.get(VoiceSessionFactRecord, fact.session_id)
        if record is None:
            db_session.add(
                VoiceSessionFactRecord(
                    session_id=fact.session_id,
                    status=fact.status,
                    termination_reason=fact.termination_reason,
                    transcript_turn_count=fact.transcript_turn_count,
                    client_diagnostics=dict(fact.client_diagnostics),
                    started_at=fact.started_at,
                    completed_at=fact.completed_at,
                    updated_at=fact.updated_at,
                )
            )
            return

        record.status = fact.status
        record.termination_reason = fact.termination_reason
        record.transcript_turn_count = fact.transcript_turn_count
        record.client_diagnostics = dict(fact.client_diagnostics)
        record.started_at = fact.started_at
        record.completed_at = fact.completed_at
        record.updated_at = fact.updated_at

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


async def save_session(session: Session) -> Session:
    return await SqlAlchemySessionRepository().save_session(session)


async def get_session(session_id: str) -> Session:
    return await SqlAlchemySessionRepository().get_session(session_id)


async def add_message(session_id: str, message: Message) -> Session:
    return await SqlAlchemySessionRepository().add_message(session_id, message)


async def list_user_sessions(user_id: str) -> list[Session]:
    return await SqlAlchemySessionRepository().list_user_sessions(user_id)


async def reset_session_store() -> None:
    await SqlAlchemySessionRepository().reset()


def build_session_repository(session_factory: AsyncSessionFactory | None = None) -> SessionRepository:
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


def _to_session_head(record: SessionRecord) -> Session:
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
        messages=[],
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


def _to_session_event(record: SessionEventRecord) -> SessionEvent:
    return SessionEvent(
        session_id=record.session_id,
        event_type=record.event_type,
        stage=record.stage,
        payload=dict(record.payload or {}),
        created_at=record.created_at,
    )


def _to_voice_session_fact(record: VoiceSessionFactRecord) -> VoiceSessionFact:
    return VoiceSessionFact(
        session_id=record.session_id,
        status=record.status,
        termination_reason=record.termination_reason,
        transcript_turn_count=record.transcript_turn_count,
        client_diagnostics=dict(record.client_diagnostics or {}),
        started_at=record.started_at,
        completed_at=record.completed_at,
        updated_at=record.updated_at,
    )
