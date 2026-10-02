"""LLM 用量 sink（Finding 10b）行为测试。

覆盖三条不变量：
1. 纯同步调用路径（无事件循环）当前线程直接写入，字段原样落库；
2. 事件循环内调用不阻塞，DB 写挪到线程池后仍然完成；
3. 写入失败只降级为 llm_usage_sink_failed warning，绝不向上抛。
"""

from __future__ import annotations

import asyncio
import logging

import pytest
import sqlalchemy as sa

from api.db.database import (
    create_all_tables,
    create_database_engine,
    create_session_factory,
)
from api.db.llm_usage_db import LlmUsageRecord, SqlAlchemyLlmUsageSink, build_llm_usage_sink


def _read_rows(engine: sa.Engine) -> list[sa.Row]:  # type: ignore[type-arg]
    with engine.connect() as conn:
        return list(
            conn.execute(
                sa.select(
                    LlmUsageRecord.model,
                    LlmUsageRecord.prompt_tokens,
                    LlmUsageRecord.completion_tokens,
                    LlmUsageRecord.total_tokens,
                ).order_by(LlmUsageRecord.id.asc())
            )
        )


def test_sink_records_usage_inline_without_event_loop(tmp_path) -> None:
    """同步调用路径：record 直接写一行，四个字段原样落库。"""
    engine = create_database_engine(f"sqlite:///{tmp_path / 'usage-sync.db'}")
    create_all_tables(engine)
    sink = SqlAlchemyLlmUsageSink(create_session_factory(engine))

    sink.record(model="demo-model", prompt_tokens=12, completion_tokens=3, total_tokens=15)

    rows = _read_rows(engine)
    assert rows == [("demo-model", 12, 3, 15)]


def test_sink_allows_null_token_fields(tmp_path) -> None:
    """字段缺省容错：上游 usage 缺 token 字段时按 NULL 落库，而非拒绝写入。"""
    engine = create_database_engine(f"sqlite:///{tmp_path / 'usage-null.db'}")
    create_all_tables(engine)
    sink = SqlAlchemyLlmUsageSink(create_session_factory(engine))

    sink.record(model="demo-model", prompt_tokens=5, completion_tokens=None, total_tokens=None)

    rows = _read_rows(engine)
    assert rows == [("demo-model", 5, None, None)]


@pytest.mark.anyio
async def test_sink_hops_to_thread_inside_event_loop(tmp_path) -> None:
    """async 调用路径：写入在线程池完成，等待在途写入后行可见且事件循环未被阻塞。"""
    engine = create_database_engine(f"sqlite:///{tmp_path / 'usage-async.db'}")
    create_all_tables(engine)
    sink = SqlAlchemyLlmUsageSink(create_session_factory(engine))

    sink.record(model="demo-model", prompt_tokens=7, completion_tokens=2, total_tokens=9)
    # fire-and-forget 的写入由 _inflight 持有强引用；等待它们完成后再断言。
    if sink._inflight:
        await asyncio.gather(*list(sink._inflight))

    rows = _read_rows(engine)
    assert rows == [("demo-model", 7, 2, 9)]


def test_sink_write_failure_degrades_to_warning(tmp_path, caplog) -> None:
    """写入失败（此处为表缺失）只记 llm_usage_sink_failed warning，不向上抛。"""
    engine = create_database_engine(f"sqlite:///{tmp_path / 'bare.db'}")  # 无 llm_usage 表
    sink = SqlAlchemyLlmUsageSink(create_session_factory(engine))

    with caplog.at_level(logging.WARNING, logger="api.db.llm_usage_db"):
        sink.record(model="demo-model", prompt_tokens=1, completion_tokens=1, total_tokens=2)

    assert "llm_usage_sink_failed" in caplog.text
    assert "demo-model" in caplog.text


def test_build_llm_usage_sink_is_singleton() -> None:
    """lru_cache 单例：provider 构造链各自注入时共享同一实例。"""
    assert build_llm_usage_sink() is build_llm_usage_sink()
