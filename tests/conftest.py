from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# SQLite 专属用例标记：CI backend-postgres job（ECHOWHALE_TEST_DATABASE_URL 指向 PG）
# 下显式 skip，skip message 必须携带理由（理由成文是验收项）。
SQLITE_ONLY_MARKER = "sqlite_only"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{SQLITE_ONLY_MARKER}(reason=None): SQLite 专属用例，PG 方言下 skip（需给 reason）",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    from tests.support.dialect import dialect_is_postgres

    if not dialect_is_postgres():
        return

    for item in items:
        marker = item.get_closest_marker(SQLITE_ONLY_MARKER)
        if marker is None:
            continue
        reason = marker.kwargs.get("reason") or "SQLite 专属用例（未写明理由）"
        item.add_marker(pytest.mark.skip(reason=f"SQLite 专属：{reason}"))


@pytest.fixture
def anyio_backend() -> str:
    from tests.support.dialect import dialect_is_postgres, ensure_psycopg_async_compatible_loop

    # psycopg async 在 Windows 默认 ProactorEventLoop 上不可用；PG 方言验证前
    # 切 Selector loop（CI ubuntu 默认即 Selector，无感）。必须在 loop 创建前
    # 调用（anyio runner 惰性建 loop），SQLite 方言不触碰策略。
    if dialect_is_postgres():
        ensure_psycopg_async_compatible_loop()
    return "asyncio"


@pytest.fixture
def dialect_engine(tmp_path):
    """方言无关 sync 引擎：PG 共享库（构建时先重置）/ SQLite tmp 文件库。

    方言分支全部收敛在 tests/support/engine.py，测试文件不得自拼 SQLite URL 字面量。
    """
    from tests.support.engine import build_dialect_sync_engine

    engine = build_dialect_sync_engine(tmp_path, "dialect")
    yield engine
    engine.dispose()


@pytest.fixture
async def dialect_async_engine(tmp_path):
    """方言无关 async 引擎：语义同 dialect_engine 的异步版（anyio 与用例同 loop）。"""
    from tests.support.engine import build_dialect_async_engine

    engine = await build_dialect_async_engine(tmp_path, "dialect")
    yield engine
    await engine.dispose()


@pytest.fixture
def span_exporter():
    """内存导出器：收集测试期间结束的 span，teardown 清空防跨用例泄漏。"""
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    yield exporter
    exporter.clear()


@pytest.fixture
def recording_tracer(monkeypatch: pytest.MonkeyPatch, span_exporter):
    """把 telemetry._tracer 整体替换为独立 SDK TracerProvider 产出的 tracer。

    隔离铁律（design 2.5）：绝不调用 trace.set_tracer_provider()——全局 provider
    只服务自动插桩且只能设一次；这里构建私有 provider + SimpleSpanProcessor +
    InMemorySpanExporter，monkeypatch 换掉模块级 _tracer，测试结束自动恢复。
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from api.common import telemetry

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("echowhale-tests"))
    return span_exporter
