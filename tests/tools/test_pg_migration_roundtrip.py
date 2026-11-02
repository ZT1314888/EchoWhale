"""pg_migration_roundtrip 往返脚本的 SQLite 口径单元测试（design §1.1）。

monkeypatch settings.database_url 到 tmp sqlite 文件后调 main()：往返全程
（含 15 个 down()）任何一步失败都会异常上抛让本用例变红。monkeypatch 隔离，
PG 口径的 backend-postgres job 里同样只写 tmp 文件、不触碰共享测试库。
"""

from __future__ import annotations

import sqlalchemy as sa

from api.core.config import settings
from tools.pg_migration_roundtrip import _alembic_head, _build_alembic_config, main


def test_roundtrip_reaches_head_with_all_tables(tmp_path, monkeypatch, capsys) -> None:
    database_path = tmp_path / "roundtrip.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")

    main()  # 重置 → upgrade → 灌种子 → downgrade → upgrade → 断言，失败即异常
    output = capsys.readouterr().out
    assert "6/6" in output  # 六步摘要全部打印

    # 独立复核（不依赖脚本自身断言）：alembic_version == head、13 张业务表齐全。
    head = _alembic_head(_build_alembic_config())
    engine = sa.create_engine(f"sqlite:///{database_path}")
    try:
        with engine.connect() as conn:
            version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == head
        tables = set(sa.inspect(engine).get_table_names())
        assert {
            "users",
            "sessions",
            "session_messages",
            "media",
            "scene_analyses",
            "llm_usage",
            "user_learning_profiles",
        } <= tables
    finally:
        engine.dispose()
