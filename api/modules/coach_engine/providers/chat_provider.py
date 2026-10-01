from __future__ import annotations

from typing import Protocol

from api.common.exceptions import ModelProviderError
from api.core.config import settings
from api.integrations.llm.base import TextStream
from api.integrations.llm.openai import OpenAICompatibleClient
from api.integrations.llm.streaming import WordChunkedTextStream
from api.modules.coach_engine.prompts.coach_prompts import COACH_SYSTEM_PROMPT
from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult
from api.modules.coach_engine.tools.dialogue_tools import build_follow_up


class ChatProvider(Protocol):
    async def reply(self, payload: CoachReplyInput) -> CoachReplyResult: ...


class StreamingChatProvider(Protocol):
    """可选能力协议：打开一条已完成连接校验的教练回复增量流。"""

    async def open_reply_stream(self, payload: CoachReplyInput) -> TextStream: ...


class MockChatProvider:
    async def reply(self, payload: CoachReplyInput) -> CoachReplyResult:
        """用场景线索拼出稳定回复，供本地开发和测试复用。"""
        return CoachReplyResult(text=_build_mock_reply(payload))

    async def open_reply_stream(self, payload: CoachReplyInput) -> TextStream:
        """mock 流按词切片吐出，模拟真实逐 token 节奏。"""
        return WordChunkedTextStream(_build_mock_reply(payload))


def _build_mock_reply(payload: CoachReplyInput) -> str:
    """回复文本只在此处生成，reply 与流式入口共用同一份内容。"""
    learner = payload.learner_message.strip() or "that"
    follow_up = build_follow_up(payload.scene)
    anchor_hint = ", ".join(payload.visual_anchors[:2])
    vocab_hint = ", ".join(payload.vocab_candidates[:2])
    history_hint = payload.recent_messages[-1].text if payload.recent_messages else learner
    return (
        f"As your {payload.role}, I understand you said '{history_hint}'. "
        f"Let's practice with {anchor_hint or vocab_hint or learner}. {follow_up}"
    )


class OpenAICompatibleChatProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        """保存远端文本模型调用所需的客户端配置。"""
        self.client = OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            stream_include_usage=settings.llm_stream_include_usage,
        )

    async def reply(self, payload: CoachReplyInput) -> CoachReplyResult:
        """调用兼容 OpenAI 的文本模型生成教练回复。"""
        user_prompt = _build_coach_user_prompt(payload)
        try:
            text = await self.client.async_complete_text(
                system_prompt=COACH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # pragma: no cover - live provider path
            raise ModelProviderError("Chat provider failed to generate reply") from exc
        return CoachReplyResult(text=text)

    async def open_reply_stream(self, payload: CoachReplyInput) -> TextStream:
        """调用兼容 OpenAI 的文本模型打开教练回复流；打开阶段失败交给上层 failover。"""
        user_prompt = _build_coach_user_prompt(payload)
        try:
            return await self.client.async_open_text_stream(
                system_prompt=COACH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # pragma: no cover - live provider path
            raise ModelProviderError("Chat provider failed to open reply stream") from exc


def _build_coach_user_prompt(payload: CoachReplyInput) -> str:
    """把场景、上下文和最近消息整理成单个用户提示词。"""
    recent_messages = [
        f"{message.role}: {message.text}"
        for message in payload.recent_messages[-settings.llm_coach_window_size :]
    ]
    return "\n".join(
        [
            f"Scene: {payload.scene}",
            f"Role: {payload.role}",
            f"Visual anchors: {', '.join(payload.visual_anchors) or 'none'}",
            f"Vocab candidates: {', '.join(payload.vocab_candidates) or 'none'}",
            (
                "Plausible scenario expansion: infer one modest social situation that fits the "
                "visible setting, such as visitor check-in in an office lounge, but avoid "
                "unsupported specifics."
            ),
            "Recent messages:",
            *recent_messages,
            f"Learner message: {payload.learner_message}",
            (
                "Write one short coach reply and one follow-up question in plain text. Keep the "
                "reply grounded in the visible evidence and existing dialogue."
            ),
        ]
    )
