"""语音收口编排（多 Agent 升级 P0，自 session_engine/agent.py 原样迁入）。

complete_voice_session 的编排水务：转写拼接与尾段去重 → 反馈（失败降级占位）
→ 复盘（失败降级模板）→ 展示名并入 → voice_fact（代数不变）+ 事件 → 原子落库
→ 档案增强分支。失败语义与迁入前逐字节一致；转写纯函数（拼接/去重/签名）
供单测直接覆盖。
"""

from __future__ import annotations

from api.common.exceptions import ValidationError as AppValidationError
from api.db.session_db import SessionRepository
from api.models.message_model import Message
from api.models.runtime_model import SessionEvent, VoiceSessionFact
from api.models.session_model import Session
from api.modules.orchestration.failure_policy import degraded_feedback_with_log
from api.modules.orchestration.profile_branch import LearnerProfileBranch
from api.modules.orchestration.protocol import FeedbackReviewAgent, ReviewSummarizerProtocol
from api.modules.orchestration.review_branch import review_copy_for_turn
from api.modules.session_engine.review_builder import build_session_review
from api.modules.session_engine.schema import (
    VoiceCompleteInput,
    VoiceCompleteResult,
)


async def run_voice_closeout(
    *,
    session_repository: SessionRepository,
    feedback_agent: FeedbackReviewAgent,
    review_agent: ReviewSummarizerProtocol,
    profile_branch: LearnerProfileBranch,
    payload: VoiceCompleteInput,
) -> VoiceCompleteResult:
    """把语音转写收束成文本会话，并补齐反馈、review 与运行时事件。"""
    session = await session_repository.get_session(payload.session_id)
    messages = build_voice_messages(session, payload)
    # build_voice_messages 已完成尾段去重：结果 = 既有消息 + 新增尾巴。
    # 仓储只追加新增部分（append-only），既有消息行保持不动，
    # 避免收口期间与文本轮并发时覆盖/删除对方消息（Finding 8）。
    new_messages = messages[len(session.messages) :]
    updated_session = session.model_copy(
        update={
            "messages": messages,
        }
    )
    last_learner_message = find_latest_user_content(payload)
    if last_learner_message is None:
        raise AppValidationError("Validation error")
    # 反馈是增值能力，与 reply/stream 同款 failure policy：失败降级占位反馈
    # （单一转换点 degraded_feedback_with_log），收口照常落库与返回。
    # 只捕获 Exception：CancelledError 等取消语义不上吞。
    feedback_degraded = False
    try:
        feedback = await feedback_agent.review(
            last_learner_message,
            updated_session.scene,
            updated_session.vocab_candidates,
        )
    except Exception as exc:  # noqa: BLE001 - 反馈失败需降级续轮而非上抛
        feedback = degraded_feedback_with_log(exc)
        feedback_degraded = True
    # 反馈已降级时复盘直接走 None 短路（对占位文案做汇总没有意义）；
    # 正常反馈路径失败/超时降级模板复盘（copy=None）。
    review_copy = await review_copy_for_turn(
        review_agent=review_agent,
        session_head=updated_session,
        learner_message=last_learner_message,
        feedback=feedback,
        feedback_degraded=feedback_degraded,
    )
    # LLM 展示名在复盘产出后并入收口快照（design 2.2）：review_copy=None
    # （mock/复盘降级）时沿用 get_session 读出的既有列值，不回闪。
    if review_copy is not None:
        updated_session = updated_session.model_copy(
            update={
                "llm_scene_title": review_copy.scene_title,
                "llm_role_label": review_copy.role_label,
            }
        )
    review = build_session_review(updated_session, feedback, copy=review_copy)
    existing_voice_fact = await session_repository.get_latest_voice_session_fact(payload.session_id)
    voice_fact = VoiceSessionFact(
        session_id=payload.session_id,
        status="completed",
        termination_reason=payload.termination_reason,
        transcript_turn_count=len(payload.conversation),
        # 收口只置状态不改代数：token_generation 必须回带既有值，否则
        # upsert 清零会让 re-bootstrap 的代数从 1 重来、旧令牌重新"复活"
        # （审计 F12 的生命周期绑定语义）。
        token_generation=(
            existing_voice_fact.token_generation if existing_voice_fact is not None else 0
        ),
        client_diagnostics=dict(payload.client_diagnostics),
        started_at=(
            existing_voice_fact.started_at
            if existing_voice_fact is not None
            else updated_session.created_at
        ),
        completed_at=review.updated_at,
        updated_at=review.updated_at,
    )
    events = [
        SessionEvent(
            session_id=payload.session_id,
            event_type="voice_finalized",
            stage="review_ready",
            payload={
                "termination_reason": payload.termination_reason,
                "conversation_turn_count": len(payload.conversation),
                "client_diagnostics": dict(payload.client_diagnostics),
            },
            created_at=review.updated_at,
        ),
        SessionEvent(
            session_id=payload.session_id,
            event_type="review_built",
            stage="review_ready",
            payload={"review_title": review.title},
            created_at=review.updated_at,
        ),
    ]
    stored_session, stored_review = await session_repository.finalize_voice_session(
        session=updated_session,
        new_messages=new_messages,
        review=review,
        voice_fact=voice_fact,
        events=events,
    )
    # 档案更新在语音收口成功之后（独立事务）：写失败只降级，不影响已提交的会话。
    await profile_branch.update_for_turn(updated_session, feedback)
    return VoiceCompleteResult(session=stored_session, review=stored_review)


def build_voice_messages(session: Session, payload: VoiceCompleteInput) -> list[Message]:
    """把语音转写拼回会话消息流，并去掉与已有消息重复的尾段。"""
    transcript: list[Message] = []
    for index, turn in enumerate(payload.conversation):
        if (
            index == 0
            and turn.role == "assistant"
            and session.messages
            and session.messages[0].role == "assistant"
            and turn.content == session.messages[0].text
        ):
            transcript.append(session.messages[0])
            continue
        transcript.append(
            Message(
                role=turn.role,
                text=turn.content,
            )
        )

    if not session.messages:
        return transcript

    remainder = list(transcript)
    if remainder and message_signature(remainder[0]) == message_signature(session.messages[0]):
        remainder = remainder[1:]

    # 语音链路会回传整段 transcript，这里按尾部重叠去重，避免重复入库。
    overlap = find_tail_overlap(existing=session.messages, incoming=remainder)
    return [*session.messages, *remainder[overlap:]]


def find_latest_user_content(payload: VoiceCompleteInput) -> str | None:
    """提取最后一条学习者发言，供反馈引擎生成最终复盘。"""
    for turn in reversed(payload.conversation):
        if turn.role == "user":
            return turn.content
    return None


def find_tail_overlap(*, existing: list[Message], incoming: list[Message]) -> int:
    """寻找旧消息尾部与新 transcript 头部的最大重叠长度。"""
    max_overlap = min(len(existing), len(incoming))
    for size in range(max_overlap, 0, -1):
        existing_tail = existing[-size:]
        incoming_head = incoming[:size]
        if all(
            message_signature(left) == message_signature(right)
            for left, right in zip(existing_tail, incoming_head, strict=False)
        ):
            return size
    return 0


def message_signature(message: Message) -> tuple[str, str]:
    """提取消息去重时使用的稳定签名。"""
    return (message.role, message.text)
