"""方言无关的测试引擎支持层：tests/ 内方言分支的唯一归属地。

为什么要把 URL 构造收敛到这里：仓储/服务测试要同时覆盖 SQLite（本地与 CI
backend job）和真实 PG（CI backend-postgres job）。若测试文件各自自拼 SQLite
URL 字面量，PG 口径会静默退化成 SQLite，方言平价名存实亡。本模块按
tests/support/dialect.py 的开关（ECHOWHALE_TEST_DATABASE_URL）分支：
- 未设置（默认）：SQLite tmp 文件库，行为与历史基线逐字节一致；
- PG：连接共享测试库，并在构建引擎后重置 schema（drop 全部 metadata 表）。

刻意不用内存库：PG 分支只有共享库一种形态，SQLite 保持既有 tmp 文件形态，
两侧各自语义统一，避免出现第三种组合。

PG 重置语义：每用例开始前 drop 全部 metadata 表。固定主键/邮箱
（sess_123、med_123、learner@example.com）让用例天然隔离，无需把几十处断言
改成随机后缀（大 diff 且更易错）；drop_all 只动 Base.metadata 里的表，
alembic_version 不在 metadata 中，因此迁移版本记录不受影响。

方言开关只认 ECHOWHALE_TEST_DATABASE_URL，禁止读 settings.database_url：
本地 .env 的 DATABASE_URL 指向 dev 库，测试不得写那里。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from api.db.database import Base, create_async_database_engine, create_database_engine
from tests.support.dialect import dialect_database_url, dialect_is_postgres, to_psycopg_url


def _sqlite_file_url(tmp_path: Path, name: str, *, async_driver: bool) -> str:
    scheme = "sqlite+aiosqlite" if async_driver else "sqlite"
    return f"{scheme}:///{tmp_path / f'{name}.db'}"


def dialect_sync_url(tmp_path: Path, name: str) -> str:
    """同步引擎 URL：PG 经 to_psycopg_url 归一化（sync 引擎不做方言转换），SQLite 落 tmp 文件库。"""
    if dialect_is_postgres():
        return to_psycopg_url(dialect_database_url())
    return _sqlite_file_url(tmp_path, name, async_driver=False)


def dialect_async_url(tmp_path: Path, name: str) -> str:
    """异步引擎 URL：PG 直接用裸 URL（create_async_database_engine 自带转换），SQLite 落 tmp 文件库。"""
    if dialect_is_postgres():
        return dialect_database_url()
    return _sqlite_file_url(tmp_path, name, async_driver=True)


def _ensure_metadata_loaded() -> None:
    """导入全部表模块，保证 Base.metadata 覆盖全部 13 张表（与 create_all_tables 同一手法）。"""
    import api.db.auth_db
    import api.db.learner_profile_db
    import api.db.llm_usage_db
    import api.db.media_db
    import api.db.scene_analysis_db
    import api.db.session_db  # noqa: F401


def reset_shared_postgres_schema(engine: Engine) -> None:
    """PG 共享库按用例重置：drop 全部 metadata 表（alembic_version 不受影响）。"""
    _ensure_metadata_loaded()
    Base.metadata.drop_all(bind=engine)


async def reset_shared_postgres_schema_async(engine: AsyncEngine) -> None:
    """异步版重置：语义同 reset_shared_postgres_schema。"""
    _ensure_metadata_loaded()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def build_dialect_sync_engine(tmp_path: Path, name: str) -> Engine:
    """自管同步引擎（不经 fixture 的测试用）：按方言取 URL，PG 先重置共享库。"""
    engine = create_database_engine(dialect_sync_url(tmp_path, name))
    if dialect_is_postgres():
        reset_shared_postgres_schema(engine)
    return engine


async def build_dialect_async_engine(tmp_path: Path, name: str) -> AsyncEngine:
    """自管异步引擎：按方言取 URL，PG 先重置共享库。"""
    engine = create_async_database_engine(dialect_async_url(tmp_path, name))
    if dialect_is_postgres():
        await reset_shared_postgres_schema_async(engine)
    return engine
