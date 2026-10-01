from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    delete,
    func,
    or_,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from api.common.enums import SessionStatus
from api.common.exceptions import InvalidStateError, NotFoundError
from api.db.database import AsyncSessionFactory, Base, get_async_session_factory
from api.models.message_model import Message
from api.models.review_model import PracticeFeedback, SessionReview
from api.models.runtime_model import SessionEvent, VoiceSessionFact
from api.models.session_model import Session

logger = logging.getLogger(__name__)


class SessionRepository(Protocol):
    async def list_recent_messages(
        self,
        session_id: str,
        *,
        limit: int,
    ) -> list[Message]: ...

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
        new_messages: list[Message],
        review: SessionReview,
        voice_fact: VoiceSessionFact,
        events: list[SessionEvent],
    ) -> tuple[Session, SessionReview]: ...

    async def save_session_review(self, review: SessionReview) -> SessionReview: ...

    async def get_session_review(self, session_id: str) -> SessionReview: ...

    async def list_user_sessions_page(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: tuple[datetime, str] | None,
    ) -> tuple[list[Session], bool, tuple[datetime, str] | None]: ...

    async def list_session_reviews_by_ids(
        self, session_ids: list[str]
    ) -> dict[str, SessionReview]: ...

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
    # 历史列表按 (user_id, updated_at) keyset 分页，复合索引与迁移 0011 保持一致。
    __table_args__ = (Index("ix_sessions_user_id_updated_at", "user_id", "updated_at"),)

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
    # (session_id, position) 唯一是消息序号的数据库级兜底：并发写同一会话
    # 分配到重复 position 时必须撞约束失败，而不是静默落库打乱回放顺序。
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_session_messages_session_position"),
    )

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
        """仅用于会话创建路径（agent.start）的全量落库。

        实现是"删除该会话全部消息后按内存快照重插"，创建时会话尚无并发写者，
        这样做安全；会话创建之后的消息追加一律走 save_reply_turn /
        finalize_voice_session 的 append 语义，禁止再调用本方法，否则会把
        并发写入的消息静默删掉（丢失更新）。
        """
        async with self._session_factory() as db_session:
            await self._upsert_session_record(db_session, session)
            # 强制先落父 session，避免在 FK 严格数据库中先写子 message。
            await db_session.flush()
            await db_session.execute(
                delete(MessageRecord).where(MessageRecord.session_id == session.id)
            )
            for position, message in enumerate(session.messages):
                db_session.add(self._to_message_record(session.id, position, message))
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

            current_position = await self._read_max_position(db_session, session_id)
            db_session.add(
                self._to_message_record(
                    session_id,
                    current_position + 1,
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
        # "读 max(position) → 写"窗口内若另一并发回复先落库，唯一约束会拒绝
        # 重复 position（Finding 7）。每次尝试用独立事务：冲突后整体回滚重开，
        # 兼容 SQLite（commit 时报错）与 PG（flush 时报错）的差异，避免半提交；
        # 重读 max 再试一次即可覆盖该竞态窗口，仍冲突说明并发方持续写入，
        # 按状态冲突上抛，交由调用方的重试语义处理。
        for attempt in range(2):
            try:
                async with self._session_factory() as db_session:
                    record = await db_session.get(SessionRecord, session_id)
                    if record is None:
                        raise NotFoundError(f"Session {session_id} not found")

                    next_position = await self._read_max_position(db_session, session_id) + 1
                    db_session.add(
                        self._to_message_record(session_id, next_position, learner_message)
                    )
                    db_session.add(
                        self._to_message_record(session_id, next_position + 1, assistant_message)
                    )
                    await self._upsert_review_record(db_session, review)
                    record.updated_at = review.updated_at
                    await db_session.commit()
                break
            except IntegrityError as exc:
                if attempt == 0:
                    logger.warning(
                        "save_reply_turn_position_conflict session_id=%s retry=true", session_id
                    )
                    continue
                raise InvalidStateError("Concurrent reply write conflict") from exc
        return await self.get_session(session_id)

    async def finalize_voice_session(
        self,
        *,
        session: Session,
        new_messages: list[Message],
        review: SessionReview,
        voice_fact: VoiceSessionFact,
        events: list[SessionEvent],
    ) -> tuple[Session, SessionReview]:
        """语音收口的 append-only 落库：既有消息行一律不动，只追加新增部分。

        new_messages 由 agent 层经 _build_voice_messages 尾段去重后传入
        （即 remainder[overlap:]）。此前实现是删除全部消息后按内存快照重插，
        语音收口与文本轮并发时会静默删掉对方刚落库的消息（Finding 8）。
        """
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionRecord, session.id)
            if record is None:
                raise NotFoundError(f"Session {session.id} not found")

            await self._upsert_session_record(db_session, session)
            await db_session.flush()

            # 只追加：position 从当前 max+1 连续分配，绝不 delete 既有消息行。
            current_position = await self._read_max_position(db_session, session.id)
            for offset, message in enumerate(new_messages):
                db_session.add(
                    self._to_message_record(session.id, current_position + 1 + offset, message)
                )

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

        return (
            await self.get_session(session.id),
            await self.get_session_review(review.session_id),
        )

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
            records = (
                await db_session.scalars(
                    statement.order_by(
                        SessionRecord.updated_at.desc(), SessionRecord.id.desc()
                    ).limit(limit + 1)
                )
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
            records = (
                await db_session.scalars(
                    select(SessionReviewRecord).where(
                        SessionReviewRecord.session_id.in_(session_ids)
                    )
                )
            ).all()
            return {record.session_id: _to_review(record) for record in records}

    async def get_session_head(self, session_id: str) -> Session:
        async with self._session_factory() as db_session:
            record = await db_session.get(SessionRecord, session_id)
            if record is None:
                raise NotFoundError(f"Session {session_id} not found")
            return _to_session_head(record)

    async def list_recent_messages(
        self,
        session_id: str,
        *,
        limit: int,
    ) -> list[Message]:
        """按 position 倒序取最近 N 条消息后回正序，供教练窗口使用。"""
        async with self._session_factory() as db_session:
            await self._ensure_session_exists(db_session, session_id)
            records = (
                await db_session.scalars(
                    select(MessageRecord)
                    .where(MessageRecord.session_id == session_id)
                    .order_by(MessageRecord.position.desc())
                    .limit(max(1, limit))
                )
            ).all()
            return [self._to_message(record) for record in reversed(records)]

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

            records_desc = (
                await db_session.scalars(
                    statement.order_by(MessageRecord.position.desc()).limit(limit + 1)
                )
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
            records = (
                await db_session.scalars(
                    select(SessionEventRecord)
                    .where(SessionEventRecord.session_id == session_id)
                    .order_by(SessionEventRecord.id.asc())
                )
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

    async def _read_max_position(self, db_session, session_id: str) -> int:
        """读取会话当前最大消息序号；无消息时返回 -1，使首个 position 从 0 开始。

        抽成独立方法同时是测试缝隙：重试路径测试用它伪造过期的 max 读值，
        无需真实并发即可稳定复现唯一约束冲突。
        """
        value = await db_session.scalar(
            select(func.coalesce(func.max(MessageRecord.position), -1)).where(
                MessageRecord.session_id == session_id
            )
        )
        return int(value)

    async def _load_messages(self, db_session, session_id: str) -> Sequence[MessageRecord]:
        result = await db_session.scalars(
            select(MessageRecord)
            .where(MessageRecord.session_id == session_id)
            .order_by(MessageRecord.position.asc())
        )
        return result.all()

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


async def reset_session_store() -> None:
    await SqlAlchemySessionRepository().reset()


def build_session_repository(
    session_factory: AsyncSessionFactory | None = None,
) -> SessionRepository:
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
