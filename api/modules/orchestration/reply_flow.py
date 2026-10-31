"""文本回复轮编排（多 Agent 升级 P0，自 session_engine/agent.py 原样迁入）。

一轮文本对话的确定性管道（Anthropic prompt chaining + parallelization 形态）：
feedback ∥ coach 并发，教练分支确认成功后有界等待复盘增强分支，原子落库，
再执行档案增强分支。失败语义（迁入前后逐字节一致）：
- 教练回复是主价值：失败整轮上抛、不落任何消息；
- 反馈是增值能力：失败降级占位反馈（failure_policy 单一转换点），本轮照常；
- 复盘是增强分支：失败/超时降级模板复盘（review_branch），事件序不变。
各 agent 经 protocol 角色协议传参，由门面在调用时解析（晚绑定契约）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from api.common.exceptions import ModelProviderError
from api.common.telemetry import TERMINAL_DEGRADED, traced_engine
from api.core.config import settings
from api.db.session_db import SessionRepository
from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.orchestration.failure_policy import (
    degraded_feedback_with_log,
    resolve_feedback,
)
from api.modules.orchestration.profile_branch import LearnerProfileBranch
from api.modules.orchestration.protocol import (
    ConversationCoachAgent,
    FeedbackReviewAgent,
    ReviewSummarizerProtocol,
)
from api.modules.orchestration.review_branch import (
    collect_review_task,
    review_copy_for_turn,
)
from api.modules.session_engine.review_builder import ReviewCopy, build_session_review
from api.modules.session_engine.schema import ReplyInput

logger = logging.getLogger(__name__)


async def run_reply_turn(
    *,
    session_repository: SessionRepository,
    feedback_agent: FeedbackReviewAgent,
    coach_agent: ConversationCoachAgent,
    review_agent: ReviewSummarizerProtocol,
    profile_branch: LearnerProfileBranch,
    payload: ReplyInput,
) -> Session:
    """并发生成反馈与教练回复，再把这一轮消息原子化落库。

    失败语义分主次：反馈是增值能力，失败时降级为占位反馈，本轮照常返回与落库；
    教练回复是主价值，失败时整轮上抛、不落任何消息。
    读路径只取会话头 + 最近窗口消息，避免每轮全量拉取整个消息历史；
    写后的全量重读保留，作为响应契约的一部分。
    学员档案在会话头后点查一次（低成本 PK 读），注入块同时喂给反馈与
    教练分支；档案更新在消息落库成功之后独立执行（增强分支，可降级）。
    """
    session_head = await session_repository.get_session_head(payload.session_id)
    recent_messages = await session_repository.list_recent_messages(
        payload.session_id,
        limit=settings.llm_coach_window_size,
    )
    learner_context, learner_cefr = await profile_branch.context_for_turn(session_head)
    # 两个分支各自打 engine span（design 2.3 终态映射）：feedback 异常按
    # degraded 记账（降级转换仍由下方 resolve_feedback 完成），coach 异常按
    # failed 记账（主价值失败整轮上抛）。span 只记账，不改任何返回/异常语义。
    feedback_result, coach_result = await asyncio.gather(
        traced_engine(
            "feedback",
            feedback_agent.review(
                payload.learner_message,
                session_head.scene,
                session_head.vocab_candidates,
                learner_context=learner_context,
            ),
            session_id=session_head.id,
            on_exception=TERMINAL_DEGRADED,
        ),
        traced_engine(
            "coach",
            coach_agent.respond(
                scene=session_head.scene,
                role=session_head.role,
                learner_message=payload.learner_message,
                visual_anchors=session_head.visual_anchors,
                vocab_candidates=session_head.vocab_candidates,
                recent_messages=recent_messages,
                learner_context=learner_context,
                learner_cefr=learner_cefr,
            ),
            session_id=session_head.id,
        ),
        return_exceptions=True,
    )
    # 反馈和回复互不依赖，并发执行可以显著缩短单轮等待时间；
    # return_exceptions 确保一侧失败时不再取消另一侧已在计费的调用。
    # 先收敛反馈（失败即降级并留 degraded 日志），再检查教练分支：
    # 两侧同时失败时，教练异常原样上抛交全局处理器，反馈失败也已留在日志里。
    feedback_degraded = isinstance(feedback_result, Exception)
    feedback = resolve_feedback(feedback_result)
    if isinstance(coach_result, BaseException):
        raise coach_result

    # 复盘 LLM 汇总（增强分支）：在教练分支确认成功之后有界等待，
    # 任何失败都降级为 None（模板复盘），不拖垮本轮。
    review_copy = await review_copy_for_turn(
        review_agent=review_agent,
        session_head=session_head,
        learner_message=payload.learner_message,
        feedback=feedback,
        feedback_degraded=feedback_degraded,
    )
    learner_message, assistant_message, review = build_reply_turn(
        session_head,
        recent_messages,
        learner_text=payload.learner_message,
        coach_text=coach_result.text,
        feedback=feedback,
        review_copy=review_copy,
    )
    stored_session = await session_repository.save_reply_turn(
        session_head.id,
        learner_message,
        assistant_message,
        review,
        review_copy=review_copy,
    )
    # 档案更新在消息落库成功之后（独立事务）：写失败只降级不影响已提交的回复轮。
    await profile_branch.update_for_turn(session_head, feedback)
    return stored_session


async def stream_reply_turn(
    *,
    session_repository: SessionRepository,
    feedback_agent: FeedbackReviewAgent,
    coach_agent: ConversationCoachAgent,
    review_agent: ReviewSummarizerProtocol,
    profile_branch: LearnerProfileBranch,
    payload: ReplyInput,
) -> AsyncIterator[tuple[str, object]]:
    """流式 reply：先回执 feedback，再逐 token 下发教练回复，成功后原子落库。

    反馈分支失败时降级为占位反馈继续：事件序 feedback → delta* → session 不变，
    本轮照常落库；教练分支失败（打不开流、中途断流、空输出）仍整轮失败、不落任何消息。
    """
    session_head = await session_repository.get_session_head(payload.session_id)
    recent_messages = await session_repository.list_recent_messages(
        payload.session_id,
        limit=settings.llm_coach_window_size,
    )
    learner_context, learner_cefr = await profile_branch.context_for_turn(session_head)
    # 流式路径同样按 design 2.3 打 engine span；feedback 异常按 degraded 记账
    # （降级转换仍在 try/except 内完成），教练 span 只覆盖"开流"阶段——
    # span 若跨 async generator 的 yield 会把中间态泄漏进消费者上下文，
    # 明确不做，消费耗时由 server span 承载（observability.md 注明）。
    feedback_task = asyncio.create_task(
        traced_engine(
            "feedback",
            feedback_agent.review(
                payload.learner_message,
                session_head.scene,
                session_head.vocab_candidates,
                learner_context=learner_context,
            ),
            session_id=session_head.id,
            on_exception=TERMINAL_DEGRADED,
        )
    )
    try:
        coach_stream = await traced_engine(
            "coach",
            coach_agent.stream_respond(
                scene=session_head.scene,
                role=session_head.role,
                learner_message=payload.learner_message,
                visual_anchors=session_head.visual_anchors,
                vocab_candidates=session_head.vocab_candidates,
                recent_messages=recent_messages,
                learner_context=learner_context,
                learner_cefr=learner_cefr,
            ),
            session_id=session_head.id,
        )
    except BaseException:
        # 回复流打不开，这一轮已注定失败；不再等待另一侧已计费的反馈调用。
        feedback_task.cancel()
        with contextlib.suppress(BaseException):
            await feedback_task
        raise

    review_task: asyncio.Task[ReviewCopy | None] | None = None
    try:
        # 反馈是增值能力：失败时降级为占位反馈，事件序与落库照常。
        # 只捕获 Exception；CancelledError 等 BaseException 不吞，取消语义保持。
        feedback_degraded = False
        try:
            feedback = await feedback_task
        except Exception as exc:  # noqa: BLE001 - 反馈失败需降级续轮而非上抛
            feedback = degraded_feedback_with_log(exc)
            feedback_degraded = True
        yield ("feedback", feedback)

        # 复盘与教练 delta 流并行生成（增强分支）：feedback 已降级时不起任务，
        # 对占位反馈做汇总没有意义；mock 模式下任务内部短路，不发起任何调用。
        if not feedback_degraded:
            review_task = asyncio.create_task(
                review_copy_for_turn(
                    review_agent=review_agent,
                    session_head=session_head,
                    learner_message=payload.learner_message,
                    feedback=feedback,
                    feedback_degraded=False,
                )
            )

        coach_chunks: list[str] = []
        async for delta in coach_stream.aiter_deltas():
            coach_chunks.append(delta)
            yield ("delta", delta)

        # 复盘收口只有一次：先有界等待任务产出，再同时喂给复盘构建与
        # 落库——重复 collect 会二次等待已取消的任务，CancelledError
        # （BaseException）会绕过降级处理器直接外抛。
        review_copy = await collect_review_task(
            session_head.id,
            review_task,
        )
        learner_message, assistant_message, review = build_reply_turn(
            session_head,
            recent_messages,
            learner_text=payload.learner_message,
            coach_text="".join(coach_chunks),
            feedback=feedback,
            review_copy=review_copy,
        )
        session = await session_repository.save_reply_turn(
            session_head.id,
            learner_message,
            assistant_message,
            review,
            review_copy=review_copy,
        )
        # 档案更新在落库成功之后、session 事件下发之前：客户端拿到
        # session 事件时，本轮的档案累积已确定（增强分支失败只降级）。
        await profile_branch.update_for_turn(session_head, feedback)
        yield ("session", session)
    finally:
        with contextlib.suppress(Exception):
            await coach_stream.aclose()
        # 失败/提前关闭路径不留悬挂的复盘任务：教练分支中断时任务可能仍在
        # 飞行，显式取消，避免轮次结束后继续消耗配额或发起 LLM 调用。
        if review_task is not None and not review_task.done():
            review_task.cancel()


def build_reply_turn(
    session_head: Session,
    recent_messages: list[Message],
    *,
    learner_text: str,
    coach_text: str,
    feedback: FeedbackResult,
    review_copy: ReviewCopy | None = None,
) -> tuple[Message, Message, SessionReview]:
    """组装一轮对话的两条消息与复盘；coach 文本为空按模型失败处理。

    输出硬顶（Finding 11）：超长模型输出在 strip 与空判定之后截断，
    防止失控输出无限撑大 Text 列与响应体；截断是防滥用硬顶而非优雅降级，
    留 coach_reply_truncated warning 供观测。整包与流式路径共用本函数。
    """
    coach_text = coach_text.strip()
    if not coach_text:
        raise ModelProviderError("Coach reply was empty")

    max_chars = settings.llm_coach_output_max_chars
    if len(coach_text) > max_chars:
        logger.warning(
            "coach_reply_truncated session_id=%s length=%s max_chars=%s",
            session_head.id,
            len(coach_text),
            max_chars,
        )
        coach_text = coach_text[:max_chars]

    learner_message = Message(role="user", text=learner_text)
    assistant_message = Message(
        role="assistant",
        text=coach_text,
        feedback=feedback.model_dump(),
    )
    reviewed_session = session_head.model_copy(
        update={"messages": [*recent_messages, learner_message, assistant_message]}
    )
    review = build_session_review(reviewed_session, feedback, copy=review_copy)
    return (learner_message, assistant_message, review)
