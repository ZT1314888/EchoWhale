"""迁移 downgrade 往返验证脚本（本地与 CI 同一条命令）。

    uv run python -m tools.pg_migration_roundtrip

为什么存在：CI backend-postgres job 此前只验证 `alembic upgrade head`，
15 个迁移的 down() 在真实 PG 上零验证。顺序刻意放在 pytest 之后——此时共享库
刚被测试踩过、处于任意状态，直接 downgrade 是非确定性的，因此脚本先重置
schema 保证从确定状态开始，再按六步执行：

1. 重置 schema（Base.metadata.drop_all + DROP TABLE IF EXISTS alembic_version）；
2. alembic upgrade head（迁移链重建）；
3. 灌种子数据——单事务、FK-safe 顺序、覆盖全部 13 张表：有数据的 schema 往下
   砍，FK/CASCADE/列依赖的 down 步骤才真正被踩到；
4. alembic downgrade base（15 个 down() 全量执行）；
5. alembic upgrade head（证明链可重放）；
6. 断言 alembic_version == head 且关键表存在；任何失败异常上抛（非零退出）。

库来源只认 settings.database_url（CI 由 DATABASE_URL env 提供；本地必须显式
pin 到 scratch 库，禁止误触 dev 库）。alembic 用 Config() + script_location
驱动、不加载 alembic.ini：env.py 的 fileConfig 会重置进程内 logger（与
tests/db/test_session_write_integrity.py::_run_alembic 同一手法）。
脚本自带 sync URL 归一化，不 import tests.support（tools 不依赖 tests）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.orm import Session

from api.common.exceptions import ConfigurationError
from api.core.config import settings
from api.db.auth_db import (
    AuthActionTokenRecord,
    RefreshTokenRecord,
    UserCredentialRecord,
    UserRecord,
)
from api.db.database import Base, create_database_engine
from api.db.learner_profile_db import UserLearningProfileRecord
from api.db.llm_usage_db import LlmUsageRecord
from api.db.media_db import MediaRecord
from api.db.scene_analysis_db import SceneAnalysisRecord
from api.db.session_db import (
    MessageRecord,
    SessionEventRecord,
    SessionRecord,
    SessionReviewRecord,
    VoiceSessionFactRecord,
)

ROOT = Path(__file__).resolve().parents[1]

# 断言与摘要抽查的关键表（= 全部 13 张业务表，与迁移链的目标 schema 一致）。
BUSINESS_TABLES = (
    "users",
    "user_credentials",
    "refresh_tokens",
    "auth_action_tokens",
    "media",
    "sessions",
    "session_messages",
    "session_reviews",
    "session_events",
    "voice_session_facts",
    "scene_analyses",
    "llm_usage",
    "user_learning_profiles",
)


def _normalize_sync_url(url: str) -> str:
    """脚本自管 sync 引擎的 URL 归一化（api 的 create_database_engine 不做转换）。

    sqlite+aiosqlite://（.env/CI backend job 常见形态）换回 sync sqlite://；
    裸 postgresql:// 补 +psycopg（psycopg2 未安装，psycopg3 是仓库唯一 PG 驱动）。
    """
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _build_alembic_config() -> Config:
    """仅给 script_location 的 Config：不加载 alembic.ini，env.py 的 fileConfig 被跳过。"""
    config = Config()
    config.set_main_option("script_location", str(ROOT / "api" / "migrations"))
    return config


def _alembic_head(config: Config) -> str:
    return str(ScriptDirectory.from_config(config).get_current_head())


def _reset_schema(engine: sa.Engine) -> int:
    """重置到确定状态：drop 全部 metadata 业务表 + alembic_version。"""
    Base.metadata.drop_all(bind=engine)
    table_count = len(Base.metadata.tables)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    return table_count


def _seed_business_tables(engine: sa.Engine) -> int:
    """单事务、FK-safe 顺序灌入 13 张表的最小行（ORM Record 类，方言无关）。

    顺序：users → user_credentials / refresh_tokens / auth_action_tokens →
    media → sessions → session_messages / session_reviews / session_events /
    voice_session_facts → scene_analyses → llm_usage → user_learning_profiles。
    只填 NOT NULL + PK/FK 字段：JSON/时间戳等列由 ORM 默认值或 server_default 兜底。
    """
    now = datetime.now(UTC)
    records: tuple[object, ...] = (
        UserRecord(
            id="user_seed",
            email="seed@example.com",
            nickname="Seed Learner",
            status="active",
            created_at=now,
            updated_at=now,
        ),
        UserCredentialRecord(
            id="cred_seed",
            user_id="user_seed",
            provider="password",
            password_hash="seed-password-hash",
            created_at=now,
            updated_at=now,
        ),
        RefreshTokenRecord(
            id="rt_seed",
            user_id="user_seed",
            token_hash="seed-refresh-token-hash",
            expires_at=now + timedelta(minutes=30),
            created_at=now,
        ),
        AuthActionTokenRecord(
            id="aat_seed",
            user_id="user_seed",
            purpose="email_verification",
            token_hash="seed-action-token-hash",
            expires_at=now + timedelta(minutes=15),
            created_at=now,
        ),
        MediaRecord(
            id="med_seed",
            user_id="user_seed",
            filename="seed.png",
            content_type="image/png",
            file_size=128,
            storage_key="media/user_seed/seed.png",
            upload_status="uploaded",
            created_at=now,
        ),
        SessionRecord(
            id="sess_seed",
            user_id="user_seed",
            media_id="med_seed",
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            status="active",
            created_at=now,
            updated_at=now,
        ),
        MessageRecord(
            id="msg_seed",
            session_id="sess_seed",
            position=0,
            role="assistant",
            text="Hi there, what can I get started for you today?",
            created_at=now,
        ),
        SessionReviewRecord(
            session_id="sess_seed",
            title="本轮回响",
            highlight="ok",
            next_try="ok",
            feedback={},
            created_at=now,
            updated_at=now,
        ),
        SessionEventRecord(
            session_id="sess_seed",
            event_type="voice_bootstrapped",
            stage="voice_active",
            created_at=now,
        ),
        VoiceSessionFactRecord(
            session_id="sess_seed",
            status="completed",
            started_at=now,
            updated_at=now,
        ),
        SceneAnalysisRecord(
            media_id="med_seed",
            status="ready",
            prompt_version="v1",
            scene="coffee_shop",
            created_at=now,
            updated_at=now,
        ),
        LlmUsageRecord(
            model="seed-model",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            owner_id="user_seed",
            session_id="sess_seed",
        ),
        UserLearningProfileRecord(user_id="user_seed"),
    )

    with Session(engine) as db_session, db_session.begin():
        # 逐条 add + flush：UOW 在无 relationship() 时并不保证按 FK 依赖排序
        # INSERT（SQLite 口径 FK 默认关闭掩盖了这一点，PG 上 auth_action_tokens
        # 先于 users 发出直接撞 FK）。与仓储层的 parent-first flush 纪律同源，
        # 种子顺序本身已按依赖排列，flush 只是把顺序钉死。
        for record in records:
            db_session.add(record)
            db_session.flush()

    # ORM 侧默认值已随 flush 展开；行数即种子规模摘要。
    return len(records)


def _assert_final_state(engine: sa.Engine, head: str) -> None:
    """断言回到 head 且关键表存在；inspector 在最终 upgrade 之后创建（无缓存问题）。"""
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == head, f"alembic_version={version!r} != head {head!r}"

    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    missing = [table for table in BUSINESS_TABLES if table not in tables]
    assert not missing, f"往返后缺失业务表: {missing}"


def main() -> None:
    """六步往返；任何失败异常上抛（进程非零退出）。"""
    database_url = settings.database_url.strip()
    if not database_url:
        raise ConfigurationError("DATABASE_URL is not configured")

    engine = create_database_engine(_normalize_sync_url(database_url))
    config = _build_alembic_config()
    head = _alembic_head(config)
    try:
        print(f"[roundtrip] 数据库: {_normalize_sync_url(database_url)}（head={head}）")

        table_count = _reset_schema(engine)
        print(f"[roundtrip] 1/6 重置 schema：drop {table_count} 张 metadata 表 + alembic_version")

        command.upgrade(config, "head")
        print(f"[roundtrip] 2/6 alembic upgrade head → {head}")

        seeded = _seed_business_tables(engine)
        print(f"[roundtrip] 3/6 灌种子数据：{len(BUSINESS_TABLES)} 张表 {seeded} 行（单事务）")

        command.downgrade(config, "base")
        print("[roundtrip] 4/6 alembic downgrade base（15 个 down() 全量执行）")

        command.upgrade(config, "head")
        print(f"[roundtrip] 5/6 alembic upgrade head（链重放）→ {head}")

        _assert_final_state(engine, head)
        print("[roundtrip] 6/6 断言通过：alembic_version == head，13 张关键表全部存在")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
