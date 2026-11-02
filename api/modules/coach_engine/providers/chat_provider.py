from __future__ import annotations

from typing import Protocol

from api.common.exceptions import ModelProviderError
from api.core.config import settings
from api.db.llm_usage_db import LlmUsageSink, build_llm_usage_sink
from api.integrations.llm.base import TextStream
from api.integrations.llm.openai import OpenAICompatibleClient
from api.integrations.llm.streaming import WordChunkedTextStream
from api.modules.coach_engine.prompts.coach_prompts import build_coach_system_prompt
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
    """回复文本只在此处生成，reply 与流式入口共用同一份内容。

    复读防线（design 2.4）：无 recent_messages 时不回落引用学习者原句（改用
    "I hear you." 中性短语），anchors/vocab 双空时也不把学习者原句当练习素材
    （改用场景中性短语）——两条路径都会让 >=4 token 的学习者消息整句复现、
    天然挂 no_echo 维度。整体保持三句形态与追问收尾不变。
    """
    follow_up = build_follow_up(payload.scene)
    anchor_hint = ", ".join(payload.visual_anchors[:2])
    vocab_hint = ", ".join(payload.vocab_candidates[:2])
    if payload.recent_messages:
        last_text = payload.recent_messages[-1].text
        opener = f"As your {payload.role}, I understand you said '{last_text}'. "
    else:
        opener = f"As your {payload.role}, I hear you. "
    return (
        f"{opener}Let's practice with {anchor_hint or vocab_hint or 'what we have here'}. "
        f"{follow_up}"
    )


class OpenAICompatibleChatProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        usage_sink: LlmUsageSink | None = None,
    ) -> None:
        """保存远端文本模型调用所需的客户端配置。

        max_tokens 与用量 sink 在构造期接入：引擎（agent）对此无感知，
        所有用该 provider 发出的教练回复共享同一输出预算与用量账本。
        """
        self.client = OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_tokens=settings.llm_coach_max_tokens,
            usage_sink=usage_sink if usage_sink is not None else build_llm_usage_sink(),
            stream_include_usage=settings.llm_stream_include_usage,
        )

    async def reply(self, payload: CoachReplyInput) -> CoachReplyResult:
        """调用兼容 OpenAI 的文本模型生成教练回复。"""
        user_prompt = _build_coach_user_prompt(payload)
        try:
            text = await self.client.async_complete_text(
                system_prompt=build_coach_system_prompt(payload.learner_cefr),
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
                system_prompt=build_coach_system_prompt(payload.learner_cefr),
                user_prompt=user_prompt,
            )
        except Exception as exc:  # pragma: no cover - live provider path
            raise ModelProviderError("Chat provider failed to open reply stream") from exc


def _build_coach_user_prompt(payload: CoachReplyInput) -> str:
    """把场景、上下文和最近消息整理成单个用户提示词。

    学员档案注入块（服务端渲染的封闭集合行）在 scene 块之后追加：
    有则加、无则省，保证无档案时提示词与历史形态逐字节一致。
    """
    recent_messages = [
        f"{message.role}: {message.text}"
        for message in payload.recent_messages[-settings.llm_coach_window_size :]
    ]
    lines = [f"Scene: {payload.scene}"]
    if payload.learner_context:
        lines.append(payload.learner_context)
    lines.extend(
        [
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
    return "\n".join(lines)
