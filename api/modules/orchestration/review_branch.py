"""复盘增强分支（多 Agent 升级 P0，自 session_engine/agent.py 原样迁入）。

复盘 LLM 汇总是增强分支（审计 Finding 20 / Orchestration failure policy）：
mock 模式下编排层短路、永不发起调用；live 失败/超时统一降级模板复盘，
绝不拖垮回复轮。engine.review span 的名称、属性与三值终态映射与迁入前
逐字节一致（P0 验收标准 3）。
"""

from __future__ import annotations

import asyncio
import logging

from api.common.telemetry import TERMINAL_DEGRADED, traced_engine
from api.core.config import settings
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.orchestration.protocol import ReviewSummarizerProtocol
from api.modules.session_engine.review_builder import ReviewCopy

logger = logging.getLogger(__name__)


async def review_copy_for_turn(
    *,
    review_agent: ReviewSummarizerProtocol,
    session_head: Session,
    learner_message: str,
    feedback: FeedbackResult,
    feedback_degraded: bool,
) -> ReviewCopy | None:
    """为单轮生成 LLM 复盘文案，外层统一打 engine.review span（design 2.3）。

    终态映射：copy 产出=ok；copy=None（mock 短路 / feedback 已降级 / 降级
    转换）=degraded；异常（含超时取消的 CancelledError）=degraded。span 只
    记账，吞异常与降级转换仍由 produce_review_copy 既有代码完成。
    """
    return await traced_engine(
        "review",
        produce_review_copy(
            review_agent=review_agent,
            session_head=session_head,
            learner_message=learner_message,
            feedback=feedback,
            feedback_degraded=feedback_degraded,
        ),
        session_id=session_head.id,
        on_exception=TERMINAL_DEGRADED,
        degraded_result=None,
    )


async def produce_review_copy(
    *,
    review_agent: ReviewSummarizerProtocol,
    session_head: Session,
    learner_message: str,
    feedback: FeedbackResult,
    feedback_degraded: bool,
) -> ReviewCopy | None:
    """复盘 LLM 汇总本体（增强分支，Orchestration failure policy）。

    mock 模式短路零调用；feedback 已降级时对占位文案做汇总没有意义；
    live 路径有界等待，超时/失败/未配 provider 一律记 degraded warning 后
    返回 None，绝不拖垮回复轮。只捕获 Exception：CancelledError 照常传播，
    客户端断连语义不变。
    """
    if settings.model_runtime_mode.lower() != "live":
        return None
    if feedback_degraded:
        return None
    try:
        return await asyncio.wait_for(
            review_agent.summarize(
                scene=session_head.scene,
                role=session_head.role,
                learner_message=learner_message,
                feedback=feedback,
            ),
            timeout=settings.llm_review_wait_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - 复盘失败需降级续轮而非上抛
        logger.warning(
            "session_review_copy_failed degraded=true session_id=%s error=%s: %s",
            session_head.id,
            type(exc).__name__,
            exc,
        )
        return None


async def collect_review_task(
    session_id: str,
    review_task: asyncio.Task[ReviewCopy | None] | None,
) -> ReviewCopy | None:
    """有界等待流式路径的复盘任务；超时/失败取消任务并降级模板复盘。

    shield 保证 wait_for 超时只取消外层等待、内层任务由这里显式取消，
    不会出现双取消；wait_for 抛出的 TimeoutError（3.11+ 即内建
    TimeoutError）是 Exception 子类，与任务失败一并降级。
    """
    if review_task is None:
        return None
    try:
        return await asyncio.wait_for(
            asyncio.shield(review_task),
            timeout=settings.llm_review_wait_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - 复盘失败需降级续轮而非上抛
        review_task.cancel()
        logger.warning(
            "session_review_copy_failed degraded=true session_id=%s error=%s: %s",
            session_id,
            type(exc).__name__,
            exc,
        )
        return None
