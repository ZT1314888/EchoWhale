"""测试侧数据库方言工具：为 CI PostgreSQL 平价验证 job 提供方言感知能力。

为什么不用 settings.database_url 做方言源：本地 .env 的 DATABASE_URL 指向
dev/评测库（PostgreSQL），若以其为方言源，本地默认跑测试就会把方言感知用例
打进 dev 库（写脏数据）。因此方言由显式开关 ECHOWHALE_TEST_DATABASE_URL 控制：
- 未设置（默认）：SQLite 自包含行为，本地与 CI SQLite job 与既有基线完全一致；
- 设置为 PG URL（CI backend-postgres job / 本地 PG 等价验证）：FK 顺序用例改在
  真实 PG 上验证，SQLite 专属用例显式 skip（理由成文）。
环境变量直读先例：tests/integration/test_r2_media_pipeline.py 的 RUN_R2_INTEGRATION。
"""

from __future__ import annotations

import asyncio
import os
import sys
import warnings

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

TEST_DATABASE_URL_ENV = "ECHOWHALE_TEST_DATABASE_URL"


def dialect_database_url() -> str:
    """测试方言开关：ECHOWHALE_TEST_DATABASE_URL，未设置返回空串（=SQLite 现状）。"""
    return os.getenv(TEST_DATABASE_URL_ENV, "").strip()


def is_postgres(url: str) -> bool:
    """判断是否 PostgreSQL URL（postgresql:// 与 postgresql+psycopg:// 均算）。"""
    return url.startswith(("postgresql://", "postgresql+psycopg://"))


def dialect_is_postgres() -> bool:
    """当前测试方言是否 PG（CI backend-postgres job / 本地 PG 等价验证）。"""
    return is_postgres(dialect_database_url())


def ensure_psycopg_async_compatible_loop() -> None:
    """Windows 默认 ProactorEventLoop 不支持 psycopg async 连接，切到 Selector。

    仅在测试方言为 PG 时才有意义（SQLite/aiosqlite 两种 loop 都能跑）；CI 的
    ubuntu runner 默认就是 Selector，调用是 no-op。必须在事件循环创建前调用
    （anyio 的 anyio_backend fixture 里、异步用例启动前）。
    """
    if sys.platform != "win32":
        return
    with warnings.catch_warnings():
        # set_event_loop_policy 在 3.14 弃用（3.16 移除），但它是干预 anyio
        # pytest 插件 loop 创建的唯一生效通道；迁 3.16 时需跟随 anyio 的
        # loop_factory 方案重审这里。
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def enforce_foreign_keys(engine: Engine | AsyncEngine) -> None:
    """按方言强制外键约束，保持 FK 顺序测试在两种方言下验证意图一致。

    SQLite 默认不强制 FK，必须用 PRAGMA foreign_keys=ON 打开（既有测试的
    原始手法）；PostgreSQL 天生强制 FK，任何连接都无需（也不能）执行 PRAGMA，
    这里按方言 no-op。SQLAlchemy 不支持在 AsyncEngine 上直接挂事件，
    统一落到 sync_engine（与仓库既有 listener 写法一致）。
    """
    target = engine.sync_engine if isinstance(engine, AsyncEngine) else engine
    if target.dialect.name != "sqlite":
        return

    @event.listens_for(target, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def to_psycopg_url(url: str) -> str:
    """把裸 postgresql:// 归一化为 postgresql+psycopg://（psycopg3，仓库唯一 PG 驱动）。

    create_database_engine（同步路径）不做方言转换，而 psycopg2 未安装，
    裸 URL 会让 SQLAlchemy 落到 psycopg2 方言并 ImportError；异步路径
    （create_async_database_engine）自带转换，统一在这里归一化保持两侧一致。
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
