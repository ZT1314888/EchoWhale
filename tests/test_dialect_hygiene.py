"""防再犯守卫：tests/ 内禁止硬编码 SQLite 引擎 URL 字面量（design §2.4）。

为什么需要守卫：方言平价的前提是测试引擎 URL 只能出自 tests/support/engine.py
（按 ECHOWHALE_TEST_DATABASE_URL 分支）。历史上十几处测试各自硬编码
sqlite://，导致 PG 口径静默退化成 SQLite 而无人察觉——纯静态扫描即可拦住
这类回归，无任何 DB 依赖，因此两种口径（SQLite / PG）下都会执行。
"""

from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# 禁止的 URL 字面量：sqlite+aiosqlite:// 的尾部包含 sqlite:// 子串，
# 但两者都显式列出，命中信息更直观。
FORBIDDEN_PATTERNS = ("sqlite://", "sqlite+aiosqlite://")

# 允许清单：key 为相对 tests/ 的 POSIX 路径，value 为保留理由（逐项成文）。
# 新增条目必须先在此写明理由，否则守卫会拒绝。
ALLOWLIST: dict[str, str] = {
    # 方言开关契约说明的文档字符串（描述 URL 形态）。
    "support/dialect.py": "方言开关 helper 的文档字符串描述 URL 形态",
    # SQLite 分支构造 tmp 文件库 URL 的唯一归属地（方言分支只允许存在于这里）。
    "support/engine.py": "SQLite 分支构造 tmp 文件库 URL 的唯一归属地",
    # 迁移链 down/up 用例（sqlite_only）：链路验证必须在 SQLite 文件库上驱动
    # alembic；PG 口径由 CI backend-postgres job 的 tools.pg_migration_roundtrip 覆盖。
    "db/test_session_write_integrity.py": "sqlite_only 迁移链用例：alembic 往返必须在 SQLite 文件库上驱动",
    # 往返脚本单元测试：脚本库来源只认 settings.database_url（刻意不走测试方言
    # 开关），用例 monkeypatch 到 tmp sqlite 文件驱动全链，两种口径下都不触真库。
    "tools/test_pg_migration_roundtrip.py": "往返脚本单测：monkeypatch settings.database_url 到 tmp sqlite 驱动脚本全链",
    # 守卫自身：检测字符串必须出现在本文件。
    "test_dialect_hygiene.py": "守卫自身：检测模式字符串必须出现在本文件",
}


def test_no_hardcoded_sqlite_urls_in_tests() -> None:
    """扫描 tests/**/*.py，出现 SQLite URL 字面量即 fail，并给出改法指引。"""
    offenders: list[str] = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        relative = path.relative_to(TESTS_DIR).as_posix()
        if relative in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        hits = [pattern for pattern in FORBIDDEN_PATTERNS if pattern in text]
        if hits:
            offenders.append(f"{relative}: {', '.join(hits)}")

    assert not offenders, (
        "tests/ 内发现硬编码 SQLite 引擎 URL（PG 口径会被静默退化成 SQLite）：\n"
        + "\n".join(f"  - {item}" for item in offenders)
        + "\n改法：引擎一律走 tests/support/engine.py 的方言 builder/fixture"
        "（dialect_engine / dialect_async_engine / build_dialect_*_engine），"
        "URL 由 ECHOWHALE_TEST_DATABASE_URL 方言开关决定；"
        "确属 SQLite-only 的用例参考 tests/db/test_session_write_integrity.py 的"
        " sqlite_only 标记模式，并把理由写进本文件的 ALLOWLIST。"
    )
