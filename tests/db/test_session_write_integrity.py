"""会话写路径完整性回归测试（Finding 7 / Finding 8）。

覆盖四条不变量：
1. (session_id, position) 唯一约束在 DB 层生效，重复 position 无法插入；
2. save_reply_turn 在唯一约束冲突后重试一次并分配到正确 position；
3. 两次尝试都冲突时按状态冲突上抛 InvalidStateError；
4. finalize_voice_session 对既有消息 append-only，绝不 delete 全表重插。
另含迁移 0011 的 up/down 可逆性验证。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from api.common.exceptions import InvalidStateError
from api.core.config import settings
from api.db.database import (
    create_all_tables_async,
    create_async_database_engine,
    create_async_session_factory,
)
from api.db.session_db import MessageRecord, SqlAlchemySessionRepository
from api.models.message_model import Message
from api.models.review_model import (
    FeedbackMetric,
    PracticeFeedback,
    SessionReview,
    UsefulWordsMetric,
)
from api.models.runtime_model import SessionEvent, VoiceSessionFact
from api.models.session_model import Session

ROOT = Path(__file__).resolve().parents[2]


def _build_review(session_id: str) -> SessionReview:
    """构造最小可用的会话复盘对象，供写路径测试复用。"""
    return SessionReview(
        session_id=session_id,
        title="本轮回响",
        highlight="ok",
        next_try="ok",
        feedback=PracticeFeedback(
            grammar=FeedbackMetric(title="Grammar", body="ok"),
            more_natural=FeedbackMetric(title="More Natural", body="ok"),
            useful_words=UsefulWordsMetric(title="Useful Words", words=["ok"], body="ok"),
            next_step=FeedbackMetric(title="Next Step", body="ok"),
        ),
    )


def _build_session(session_id: str, messages: list[Message]) -> Session:
    return Session(
        id=session_id,
        user_id="demo-user",
        media_id=None,
        scene="coffee_shop",
        role="barista",
        opener="Hi there",
        messages=messages,
    )


async def _save_session_with_messages(
    repository: SqlAlchemySessionRepository, session_id: str, count: int
) -> Session:
    """落库一个带 count 条消息的会话，position 从 0 连续编号。"""
    session = _build_session(
        session_id,
        [
            Message(id=f"msg_{session_id}_{i}", role="assistant", text=f"line {i}")
            for i in range(count)
        ],
    )
    await repository.save_session(session)
    return session


async def _fetch_message_rows(engine: AsyncEngine, session_id: str) -> list[tuple[str, int]]:
    """按 position 升序取 (消息 id, position)，用于断言行身份与序号连续性。"""
    factory = create_async_session_factory(engine)
    async with factory() as db_session:
        result = await db_session.execute(
            select(MessageRecord.id, MessageRecord.position)
            .where(MessageRecord.session_id == session_id)
            .order_by(MessageRecord.position.asc())
        )
        return [(row[0], row[1]) for row in result.all()]


@pytest.mark.anyio
async def test_duplicate_position_is_rejected_by_database_constraint(tmp_path) -> None:
    """唯一约束在 DB 层兜底：同会话重复 position 直接 IntegrityError（Finding 7）。"""
    engine = create_async_database_engine(f"sqlite:///{tmp_path / 'position-unique.db'}")
    await create_all_tables_async(engine)
    repository = SqlAlchemySessionRepository(create_async_session_factory(engine))

    session = await _save_session_with_messages(repository, "sess_unique", count=1)
    assert session.messages[0].id == "msg_sess_unique_0"

    factory = create_async_session_factory(engine)
    async with factory() as db_session:
        db_session.add(
            MessageRecord(
                id="msg_duplicate_position",
                session_id="sess_unique",
                position=0,
                role="user",
                text="dup",
                created_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.commit()


@pytest.mark.anyio
async def test_save_reply_turn_retries_once_after_position_conflict(
    tmp_path, monkeypatch, caplog
) -> None:
    """首次写入撞唯一约束后回滚重读 max(position) 重试，两条消息序号正确不重复。"""
    engine = create_async_database_engine(f"sqlite:///{tmp_path / 'retry-conflict.db'}")
    await create_all_tables_async(engine)
    repository = SqlAlchemySessionRepository(create_async_session_factory(engine))
    await _save_session_with_messages(repository, "sess_retry", count=2)

    original_read = repository._read_max_position
    calls = {"count": 0}

    async def stale_first_read(db_session, session_id: str) -> int:
        # 测试缝隙：首次尝试伪造过期的 max 读值，使写入的 position=1 撞既有行。
        calls["count"] += 1
        if calls["count"] == 1:
            return 0
        return await original_read(db_session, session_id)

    monkeypatch.setattr(repository, "_read_max_position", stale_first_read)

    learner = Message(id="msg_retry_learner", role="user", text="latte please")
    assistant = Message(id="msg_retry_assistant", role="assistant", text="Sure, which size?")

    with caplog.at_level(logging.WARNING, logger="api.db.session_db"):
        updated = await repository.save_reply_turn(
            "sess_retry", learner, assistant, _build_review("sess_retry")
        )

    assert calls["count"] == 2
    rows = await _fetch_message_rows(engine, "sess_retry")
    assert rows == [
        ("msg_sess_retry_0", 0),
        ("msg_sess_retry_1", 1),
        ("msg_retry_learner", 2),
        ("msg_retry_assistant", 3),
    ]
    assert [message.id for message in updated.messages[-2:]] == [
        "msg_retry_learner",
        "msg_retry_assistant",
    ]
    assert "save_reply_turn_position_conflict" in caplog.text
    assert "retry=true" in caplog.text
    loaded_review = await repository.get_session_review("sess_retry")
    assert loaded_review.title == "本轮回响"


@pytest.mark.anyio
async def test_save_reply_turn_raises_invalid_state_error_when_retry_also_conflicts(
    tmp_path, monkeypatch
) -> None:
    """两次尝试都撞约束说明并发方持续写入，按状态冲突收敛为 InvalidStateError。"""
    engine = create_async_database_engine(f"sqlite:///{tmp_path / 'retry-exhausted.db'}")
    await create_all_tables_async(engine)
    repository = SqlAlchemySessionRepository(create_async_session_factory(engine))
    await _save_session_with_messages(repository, "sess_deadlock", count=2)

    calls = {"count": 0}

    async def always_stale_read(db_session, session_id: str) -> int:
        calls["count"] += 1
        return 0  # 每次都返回过期值 → 两次尝试都写入 position=1 → 都撞约束

    monkeypatch.setattr(repository, "_read_max_position", always_stale_read)

    with pytest.raises(InvalidStateError, match="Concurrent reply write conflict"):
        await repository.save_reply_turn(
            "sess_deadlock",
            Message(id="msg_dead_learner", role="user", text="hi"),
            Message(id="msg_dead_assistant", role="assistant", text="hello"),
            _build_review("sess_deadlock"),
        )

    assert calls["count"] == 2


@pytest.mark.anyio
async def test_finalize_voice_session_appends_without_touching_existing_messages(tmp_path) -> None:
    """语音收口 append-only：既有消息行原样保留，新消息 position 接续（Finding 8）。"""
    engine = create_async_database_engine(f"sqlite:///{tmp_path / 'finalize-append.db'}")
    await create_all_tables_async(engine)
    repository = SqlAlchemySessionRepository(create_async_session_factory(engine))

    session = await _save_session_with_messages(repository, "sess_append", count=1)
    await repository.save_reply_turn(
        "sess_append",
        Message(id="msg_text_learner", role="user", text="iced latte please"),
        Message(id="msg_text_assistant", role="assistant", text="Sure, which size?"),
        _build_review("sess_append"),
    )
    rows_before = await _fetch_message_rows(engine, "sess_append")
    assert rows_before == [
        ("msg_sess_append_0", 0),
        ("msg_text_learner", 1),
        ("msg_text_assistant", 2),
    ]

    # 只监听 finalize 期间发出的 SQL：save_session 创建路径的 delete 是允许的，
    # 收口阶段绝不允许再出现对 session_messages 的全表删除。
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_statement(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        statements.append(statement)

    review = _build_review("sess_append")
    voice_fact = VoiceSessionFact(
        session_id="sess_append",
        status="completed",
        termination_reason="user_ended",
        transcript_turn_count=3,
        completed_at=review.updated_at,
        updated_at=review.updated_at,
    )
    events = [
        SessionEvent(
            session_id="sess_append",
            event_type="voice_finalized",
            stage="review_ready",
            payload={"termination_reason": "user_ended"},
            created_at=review.updated_at,
        )
    ]
    voice_learner = Message(id="msg_voice_learner", role="user", text="one more coffee")
    voice_assistant = Message(id="msg_voice_assistant", role="assistant", text="Coming right up.")
    finalized_session = session.model_copy(
        update={
            "messages": [
                *session.messages,
                Message(id="msg_text_learner", role="user", text="iced latte please"),
                Message(id="msg_text_assistant", role="assistant", text="Sure, which size?"),
                voice_learner,
                voice_assistant,
            ]
        }
    )

    stored_session, stored_review = await repository.finalize_voice_session(
        session=finalized_session,
        new_messages=[voice_learner, voice_assistant],
        review=review,
        voice_fact=voice_fact,
        events=events,
    )

    rows_after = await _fetch_message_rows(engine, "sess_append")
    # 既有消息行身份不变（append-only），新消息 position 从当前 max+1 连续分配。
    assert rows_after == [
        ("msg_sess_append_0", 0),
        ("msg_text_learner", 1),
        ("msg_text_assistant", 2),
        ("msg_voice_learner", 3),
        ("msg_voice_assistant", 4),
    ]
    assert [message.id for message in stored_session.messages] == [row[0] for row in rows_after]
    assert stored_review.title == "本轮回响"
    assert not any("delete from session_messages" in statement.lower() for statement in statements)
    loaded_fact = await repository.get_latest_voice_session_fact("sess_append")
    assert loaded_fact is not None
    assert loaded_fact.status == "completed"
    loaded_events = await repository.list_session_events("sess_append")
    assert [item.event_type for item in loaded_events] == ["voice_finalized"]


def _run_alembic(tmp_path, monkeypatch) -> tuple[sa.Engine, Config]:
    """在独立 SQLite 文件库上跑完整迁移链，返回可检查的同步引擎。"""
    database_url = f"sqlite:///{tmp_path / 'migrations.db'}"
    monkeypatch.setattr(settings, "database_url", database_url)
    # 不加载 alembic.ini：env.py 里的 fileConfig 会在测试进程中禁用既有 logger，
    # 破坏后续用例的 caplog；只给 script_location 即可驱动同一套迁移脚本。
    config = Config()
    config.set_main_option("script_location", str(ROOT / "api" / "migrations"))
    command.upgrade(config, "head")
    return sa.create_engine(database_url), config


def _insert_duplicate_positions(engine: sa.Engine) -> None:
    """连续插入两条同 (session_id, position) 的行；约束存在时第二条必然失败。"""
    with engine.begin() as conn:
        for suffix in ("a", "b"):
            conn.execute(
                sa.text(
                    "INSERT INTO session_messages (id, session_id, position, role, text, created_at) "
                    "VALUES (:id, :session_id, :position, 'user', 'dup', :ts)"
                ),
                {
                    "id": f"msg_dup_{suffix}",
                    "session_id": "sess_migrated",
                    "position": 0,
                    "ts": "2026-10-01 00:00:00.000000",
                },
            )


def test_migration_0011_up_and_down_are_reversible(tmp_path, monkeypatch) -> None:
    """迁移链完整：up 到 head 后约束与复合索引生效，downgrade 到 0010 后两者消失。"""
    engine, config = _run_alembic(tmp_path, monkeypatch)

    inspector = sa.inspect(engine)
    index_names = {index["name"] for index in inspector.get_indexes("sessions")}
    assert "ix_sessions_user_id_updated_at" in index_names
    # 约束生效的行为断言：同 (session_id, position) 第二次插入必须被拒绝。
    with pytest.raises(IntegrityError):
        _insert_duplicate_positions(engine)

    command.downgrade(config, "20260930_0010")

    inspector = sa.inspect(engine)
    index_names = {index["name"] for index in inspector.get_indexes("sessions")}
    assert "ix_sessions_user_id_updated_at" not in index_names
    # 约束已随 downgrade 移除：同样数据可以插入成功。
    _insert_duplicate_positions(engine)


def test_migration_0012_llm_usage_up_and_down_are_reversible(tmp_path, monkeypatch) -> None:
    """迁移链完整：up 到 head 后 llm_usage 可写入且 created_at 有服务端默认值，
    downgrade 到 0011 后表随索引一起消失。"""
    engine, config = _run_alembic(tmp_path, monkeypatch)

    inspector = sa.inspect(engine)
    assert "llm_usage" in inspector.get_table_names()
    with engine.begin() as conn:
        # 不提供 created_at：验证 server_default 在 SQLite 下同样生效。
        conn.execute(
            sa.text(
                "INSERT INTO llm_usage (model, prompt_tokens, completion_tokens, total_tokens) "
                "VALUES ('demo-model', 12, 3, 15)"
            )
        )
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT model, prompt_tokens, total_tokens, created_at FROM llm_usage")
        ).one()
    assert row[0] == "demo-model"
    assert row[1] == 12
    assert row[2] == 15
    assert row[3] is not None

    command.downgrade(config, "20261001_0011")

    inspector = sa.inspect(engine)
    assert "llm_usage" not in inspector.get_table_names()


def test_migration_0014_llm_display_name_columns_up_and_down(tmp_path, monkeypatch) -> None:
    """迁移 0014（PRD v0.5 候选②）：up 到 head 后 sessions 带两展示名可空列，
    旧行读出 NULL；downgrade 到 0013 后两列消失。"""
    engine, config = _run_alembic(tmp_path, monkeypatch)

    columns = {column["name"] for column in sa.inspect(engine).get_columns("sessions")}
    assert "llm_scene_title" in columns
    assert "llm_role_label" in columns
    with engine.begin() as conn:
        # 旧行（迁移前既有会话）不受影响：新列保持 NULL，消费侧走确定性路径。
        conn.execute(
            sa.text(
                "INSERT INTO sessions (id, user_id, scene, role, opener, status, "
                "visual_anchors, vocab_candidates, labels, created_at, updated_at) "
                "VALUES ('sess_old', 'demo-user', 'gym', 'coach', 'Hi', 'active', "
                "'[]', '[]', '[]', '2026-10-06 00:00:00.000000', '2026-10-06 00:00:00.000000')"
            )
        )
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT llm_scene_title, llm_role_label FROM sessions WHERE id = 'sess_old'")
        ).one()
    assert row[0] is None
    assert row[1] is None

    command.downgrade(config, "20261002_0013")

    columns = {column["name"] for column in sa.inspect(engine).get_columns("sessions")}
    assert "llm_scene_title" not in columns
    assert "llm_role_label" not in columns
