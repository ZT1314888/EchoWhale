from __future__ import annotations

from sqlalchemy import event

from api.db.database import create_all_tables, create_database_engine, create_session_factory
from api.db.session_db import SqlAlchemySessionRepository
from api.models.message_model import Message
from api.models.session_model import Session


def test_save_session_persists_parent_before_messages_when_foreign_keys_are_enforced() -> None:
    engine = create_database_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    create_all_tables(engine)
    repository = SqlAlchemySessionRepository(create_session_factory(engine))

    session = Session(
        id="sess_fk_order",
        user_id="demo-user",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["coffee"],
        messages=[
            Message(
                id="msg_fk_order_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )

    saved = repository.save_session(session)

    assert saved.id == "sess_fk_order"
    assert [message.id for message in saved.messages] == ["msg_fk_order_1"]
