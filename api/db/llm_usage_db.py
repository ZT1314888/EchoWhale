"""LLM 用量账本（Finding 10b）：按 model 记录每次调用的 token 消耗。

该表只写不读、无多表事务组合需求，因此按 auth 仓库同款同步域实现；
异步调用路径由 sink 内部把 DB 写挪到线程池，不阻塞事件循环。
owner/session 归因：record 在调用线程（事件循环）上从请求上下文捕获，
以参数传入线程池写入——ContextVar 不跨线程传播，线程内读必为 None。
无请求上下文（启动期 / 后台任务 / session_start 创建前调用）记 NULL，
归因缺失不报错，旁路纪律与 sink 其余失败路径一致。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from functools import lru_cache
from typing import Protocol

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.common.request_context import get_request_owner, get_request_session
from api.db.database import Base, SessionFactory, get_session_factory

logger = logging.getLogger(__name__)


class LlmUsageSink(Protocol):
    """用量落库旁路接口：同步签名，失败由调用方（客户端）降级为 warning。"""

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
    ) -> None: ...


class LlmUsageRecord(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 归因列可空（迁移 0015）：owner 形如 user:<uuid> / visitor:<uuid>，
    # session 形如 sess_<uuid>；只写不读，暂不加索引，归因查询需求出现时再补。
    owner_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class SqlAlchemyLlmUsageSink:
    """默认用量 sink：insert-and-commit 单行写入。

    事件循环内调用时把 DB 写挪到默认线程池（fire-and-forget），保证 async
    调用路径不阻塞；纯同步路径直接当前线程写。线程内异常无法回到客户端的
    try/except，就地降级为 warning——用量记录是旁路观测，不是业务依赖。
    """

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        # session_factory 允许为 None：延迟到首次写入时再解析，让
        # build_llm_usage_sink() 单例能在无 DATABASE_URL 的构造期安全创建。
        self._session_factory = session_factory
        self._inflight: set[asyncio.Future[None]] = set()

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
    ) -> None:
        # 归因必须在调用线程上先捕获：async 路径经 run_in_executor 换线程
        # 执行 _write，ContextVar 不跨线程传播，线程内读取只会得到 None。
        owner_id = get_request_owner()
        session_id = get_request_session()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 无事件循环（纯同步调用路径）：与 auth 仓库同域，当前线程直接写。
            self._write(model, prompt_tokens, completion_tokens, total_tokens, owner_id, session_id)
            return
        # 事件循环内：线程池执行 + fire-and-forget；持有 future 强引用防止包装器被 GC。
        future = loop.run_in_executor(
            None,
            self._write,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            owner_id,
            session_id,
        )
        self._inflight.add(future)
        future.add_done_callback(self._inflight.discard)

    def _write(
        self,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        owner_id: str | None,
        session_id: str | None,
    ) -> None:
        try:
            session_factory = self._session_factory or get_session_factory()
            with session_factory() as session:
                session.add(
                    LlmUsageRecord(
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        # 归因缺失（无请求上下文）原样带 None，不报错不阻断。
                        owner_id=owner_id,
                        session_id=session_id,
                    )
                )
                session.commit()
        except Exception as exc:  # noqa: BLE001 - sink 失败必须与主流程隔离，就地记 warning
            logger.warning(
                "llm_usage_sink_failed model=%s error=%s: %s", model, type(exc).__name__, exc
            )


@lru_cache
def build_llm_usage_sink() -> LlmUsageSink:
    """进程级单例：provider 构造链各自注入同一 sink，避免重复建工厂。"""
    return SqlAlchemyLlmUsageSink()
