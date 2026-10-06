"""LLM 用量 sink（Finding 10b）行为测试。

覆盖四条不变量：
1. 纯同步调用路径（无事件循环）当前线程直接写入，字段原样落库；
2. 事件循环内调用不阻塞，DB 写挪到线程池后仍然完成；
3. 写入失败只降级为 llm_usage_sink_failed warning，绝不向上抛；
4. owner/session 归因在调用线程捕获后随行落库（含线程池路径），
   无请求上下文时 NULL 落库、不抛错。
"""

from __future__ import annotations

import asyncio
import logging

import pytest
import sqlalchemy as sa

from api.common.request_context import (
    reset_request_owner,
    reset_request_session,
    set_request_owner,
    set_request_session,
)
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


def _read_attribution_rows(engine: sa.Engine) -> list[tuple[str | None, str | None]]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                sa.select(LlmUsageRecord.owner_id, LlmUsageRecord.session_id).order_by(
                    LlmUsageRecord.id.asc()
                )
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


def test_sink_records_null_attribution_without_request_context(tmp_path) -> None:
    """无请求上下文（启动期 / 后台任务）：归因列 NULL 落库，不抛错（旁路纪律）。"""
    engine = create_database_engine(f"sqlite:///{tmp_path / 'usage-noctx.db'}")
    create_all_tables(engine)
    sink = SqlAlchemyLlmUsageSink(create_session_factory(engine))

    sink.record(model="demo-model", prompt_tokens=1, completion_tokens=1, total_tokens=2)

    assert _read_attribution_rows(engine) == [(None, None)]


def test_sink_persists_attribution_on_sync_path(tmp_path) -> None:
    """同步路径：调用线程上的 owner/session 上下文随行落库（访客 owner 照记）。"""
    engine = create_database_engine(f"sqlite:///{tmp_path / 'usage-sync-attr.db'}")
    create_all_tables(engine)
    sink = SqlAlchemyLlmUsageSink(create_session_factory(engine))

    owner_token = set_request_owner("visitor:v-1")
    session_token = set_request_session("sess_sync")
    try:
        sink.record(model="demo-model", prompt_tokens=4, completion_tokens=1, total_tokens=5)
    finally:
        reset_request_session(session_token)
        reset_request_owner(owner_token)

    assert _read_attribution_rows(engine) == [("visitor:v-1", "sess_sync")]


@pytest.mark.anyio
async def test_sink_persists_attribution_captured_on_event_loop_thread(tmp_path) -> None:
    """async 路径：归因必须在事件循环线程上捕获后以参数传入线程池。

    ContextVar 不跨线程传播——若在线程内读取，run_in_executor 的工作线程上
    只会拿到 None，行归因全部丢失。等待在途写入后断言归因仍然命中。
    """
    engine = create_database_engine(f"sqlite:///{tmp_path / 'usage-async-attr.db'}")
    create_all_tables(engine)
    sink = SqlAlchemyLlmUsageSink(create_session_factory(engine))

    owner_token = set_request_owner("user:u-1")
    session_token = set_request_session("sess_async")
    try:
        sink.record(model="demo-model", prompt_tokens=7, completion_tokens=2, total_tokens=9)
        if sink._inflight:
            await asyncio.gather(*list(sink._inflight))
    finally:
        reset_request_session(session_token)
        reset_request_owner(owner_token)

    assert _read_attribution_rows(engine) == [("user:u-1", "sess_async")]
