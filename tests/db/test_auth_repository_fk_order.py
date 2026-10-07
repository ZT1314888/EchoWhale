"""auth 仓储 FK 写入顺序回归：父行（users/user_credentials）必须先于子行落库。

方言平价说明：SQLite 口径靠 PRAGMA foreign_keys=ON 打开强制（enforce_foreign_keys
helper 内封装）；PG 口径（ECHOWHALE_TEST_DATABASE_URL 指向 PG，CI backend-postgres
job）天然强制 FK，直接在真实 PG 上验证同一写入顺序。共享库多次运行不能残留
旧行干扰断言，所有 ID/邮箱/token hash 带 per-test 随机后缀。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from api.db.auth_db import SqlAlchemyAuthRepository
from api.db.database import create_all_tables, create_session_factory
from api.models.user_model import RefreshTokenRecordModel, User
from tests.support.dialect import enforce_foreign_keys


def test_create_user_persists_parent_before_credentials_when_foreign_keys_are_enforced(
    dialect_engine,
) -> None:
    engine = dialect_engine
    enforce_foreign_keys(engine)
    run_id = uuid4().hex[:8]

    create_all_tables(engine)
    repository = SqlAlchemyAuthRepository(create_session_factory(engine))

    user = User(
        id=f"user_fk_order_{run_id}",
        email=f"learner-{run_id}@example.com",
        nickname="Echo Learner",
    )

    created = repository.create_user(user=user, password_hash="hashed-password")

    stored = repository.get_user_by_email(f"learner-{run_id}@example.com")

    assert created.id == f"user_fk_order_{run_id}"
    assert stored is not None
    assert stored.id == f"user_fk_order_{run_id}"


def test_rotate_refresh_token_consumes_old_token_only_once(dialect_engine) -> None:
    engine = dialect_engine
    enforce_foreign_keys(engine)
    run_id = uuid4().hex[:8]

    create_all_tables(engine)
    repository = SqlAlchemyAuthRepository(create_session_factory(engine))
    repository.create_user(
        user=User(
            id=f"user_rotate_{run_id}",
            email=f"rotate-{run_id}@example.com",
            nickname="Rotate Learner",
        ),
        password_hash="hashed-password",
    )

    now = datetime.now(UTC)
    repository.save_refresh_token(
        RefreshTokenRecordModel(
            id=f"rt_old_{run_id}",
            user_id=f"user_rotate_{run_id}",
            token_hash=f"old-hash-{run_id}",
            expires_at=now + timedelta(minutes=30),
            created_at=now,
        )
    )

    first_user_id = repository.rotate_refresh_token(
        token_hash=f"old-hash-{run_id}",
        replacement_token=RefreshTokenRecordModel(
            id=f"rt_new_{run_id}",
            user_id=f"user_rotate_{run_id}",
            token_hash=f"new-hash-{run_id}",
            expires_at=now + timedelta(minutes=45),
            created_at=now,
        ),
        revoked_at=now,
        now=now,
    )
    second_user_id = repository.rotate_refresh_token(
        token_hash=f"old-hash-{run_id}",
        replacement_token=RefreshTokenRecordModel(
            id=f"rt_other_{run_id}",
            user_id=f"user_rotate_{run_id}",
            token_hash=f"other-hash-{run_id}",
            expires_at=now + timedelta(minutes=45),
            created_at=now,
        ),
        revoked_at=now,
        now=now,
    )

    rotated_old = repository.get_refresh_token(f"old-hash-{run_id}")
    rotated_new = repository.get_refresh_token(f"new-hash-{run_id}")

    assert first_user_id == f"user_rotate_{run_id}"
    assert second_user_id is None
    assert rotated_old is not None
    assert rotated_old.revoked_at is not None
    assert rotated_new is not None
    assert rotated_new.revoked_at is None
