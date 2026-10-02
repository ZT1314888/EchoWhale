from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import event

from api.db.auth_db import SqlAlchemyAuthRepository
from api.db.database import create_all_tables, create_database_engine, create_session_factory
from api.models.user_model import RefreshTokenRecordModel, User


def test_create_user_persists_parent_before_credentials_when_foreign_keys_are_enforced() -> None:
    engine = create_database_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    create_all_tables(engine)
    repository = SqlAlchemyAuthRepository(create_session_factory(engine))

    user = User(
        id="user_fk_order",
        email="learner@example.com",
        nickname="Echo Learner",
    )

    created = repository.create_user(user=user, password_hash="hashed-password")

    stored = repository.get_user_by_email("learner@example.com")

    assert created.id == "user_fk_order"
    assert stored is not None
    assert stored.id == "user_fk_order"


def test_rotate_refresh_token_consumes_old_token_only_once() -> None:
    engine = create_database_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    create_all_tables(engine)
    repository = SqlAlchemyAuthRepository(create_session_factory(engine))
    repository.create_user(
        user=User(
            id="user_rotate",
            email="rotate@example.com",
            nickname="Rotate Learner",
        ),
        password_hash="hashed-password",
    )

    now = datetime.now(UTC)
    repository.save_refresh_token(
        RefreshTokenRecordModel(
            id="rt_old",
            user_id="user_rotate",
            token_hash="old-hash",
            expires_at=now + timedelta(minutes=30),
            created_at=now,
        )
    )

    first_user_id = repository.rotate_refresh_token(
        token_hash="old-hash",
        replacement_token=RefreshTokenRecordModel(
            id="rt_new",
            user_id="user_rotate",
            token_hash="new-hash",
            expires_at=now + timedelta(minutes=45),
            created_at=now,
        ),
        revoked_at=now,
        now=now,
    )
    second_user_id = repository.rotate_refresh_token(
        token_hash="old-hash",
        replacement_token=RefreshTokenRecordModel(
            id="rt_other",
            user_id="user_rotate",
            token_hash="other-hash",
            expires_at=now + timedelta(minutes=45),
            created_at=now,
        ),
        revoked_at=now,
        now=now,
    )

    rotated_old = repository.get_refresh_token("old-hash")
    rotated_new = repository.get_refresh_token("new-hash")

    assert first_user_id == "user_rotate"
    assert second_user_id is None
    assert rotated_old is not None
    assert rotated_old.revoked_at is not None
    assert rotated_new is not None
    assert rotated_new.revoked_at is None
