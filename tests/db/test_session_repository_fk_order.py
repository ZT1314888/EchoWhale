"""session 仓储 FK 写入顺序回归：会话头（父）必须先于 session_messages（子）落库。

方言平价说明：SQLite 口径靠 PRAGMA foreign_keys=ON 打开强制（enforce_foreign_keys
helper 内封装）；PG 口径（ECHOWHALE_TEST_DATABASE_URL 指向 PG，CI backend-postgres
job）天然强制 FK，直接在真实 PG 上验证同一写入顺序。session id 带 per-test
随机后缀，防共享库多次运行的旧行残留。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from api.db.database import create_all_tables_async, create_async_session_factory
from api.db.session_db import SqlAlchemySessionRepository
from api.models.message_model import Message
from api.models.session_model import Session
from tests.support.dialect import enforce_foreign_keys


@pytest.mark.anyio
async def test_save_session_persists_parent_before_messages_when_foreign_keys_are_enforced(
    dialect_async_engine,
) -> None:
    engine = dialect_async_engine
    enforce_foreign_keys(engine)
    run_id = uuid4().hex[:8]

    await create_all_tables_async(engine)
    repository = SqlAlchemySessionRepository(create_async_session_factory(engine))

    session = Session(
        id=f"sess_fk_order_{run_id}",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["coffee"],
        messages=[
            Message(
                id=f"msg_fk_order_1_{run_id}",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )

    saved = await repository.save_session(session)

    assert saved.id == f"sess_fk_order_{run_id}"
    assert [message.id for message in saved.messages] == [f"msg_fk_order_1_{run_id}"]
