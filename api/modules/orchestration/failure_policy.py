"""协作层失败策略（多 Agent 升级 P0，自 session_engine/agent.py 原样迁入）。

这是 reply / 语音收口两条链路共用的「反馈是增值能力」failure policy：
反馈分支失败降级为占位反馈，本轮照常返回与落库；教练分支失败整轮上抛。
只捕获 Exception：CancelledError 等 BaseException 不吞，取消语义保持。
降级日志事件名（session_reply_branch_failed）与迁入前保持一致，运维口径不变。
"""

from __future__ import annotations

import logging

from api.modules.feedback_engine.schema import FeedbackResult

logger = logging.getLogger(__name__)


def build_degraded_feedback() -> FeedbackResult:
    """构造反馈降级占位结果。

    每次新建实例而非共享单例，避免调用方意外改动可变字段互相影响；
    文案诚实标注本轮失败并预告下一轮恢复，前端按普通反馈卡片渲染即可。
    """
    return FeedbackResult(
        grammar="本轮反馈生成失败，请继续对话；下一轮反馈会照常返回。",
        more_natural="（本轮没有更自然表达建议）",
        useful_words=[],
    )


def degraded_feedback_with_log(exc: Exception) -> FeedbackResult:
    """反馈分支失败的单一降级转换点：记 degraded warning 后返回占位反馈。

    沿用 session_reply_branch_failed 事件名并补充 degraded=true，
    运维可凭该标记区分"降级成功"与"正常生成"。
    """
    logger.warning(
        "session_reply_branch_failed branch=feedback degraded=true error=%s: %s",
        type(exc).__name__,
        exc,
    )
    return build_degraded_feedback()


def resolve_feedback(result: object) -> FeedbackResult:
    """把 gather 的 return_exceptions 结果收敛成 FeedbackResult。

    成功原样返回；Exception 降级为占位反馈让本轮继续；
    CancelledError 等 BaseException 原样上抛，不吞取消语义。
    """
    if isinstance(result, Exception):
        return degraded_feedback_with_log(result)
    if isinstance(result, BaseException):
        raise result
    return result
