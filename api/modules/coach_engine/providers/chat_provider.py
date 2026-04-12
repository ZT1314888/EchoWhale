from __future__ import annotations

from typing import Protocol

from api.common.exceptions import ConfigurationError
from api.common.exceptions import ModelProviderError
from api.core.config import settings
from api.integrations.llm.openai import OpenAICompatibleClient
from api.modules.coach_engine.prompts.coach_prompts import COACH_SYSTEM_PROMPT
from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult
from api.modules.coach_engine.tools.dialogue_tools import build_follow_up


class ChatProvider(Protocol):
    async def reply(self, payload: CoachReplyInput) -> CoachReplyResult: ...


class MockChatProvider:
    async def reply(self, payload: CoachReplyInput) -> CoachReplyResult:
        """用场景线索拼出稳定回复，供本地开发和测试复用。"""
        learner = payload.learner_message.strip() or "that"
        follow_up = build_follow_up(payload.scene)
        anchor_hint = ", ".join(payload.visual_anchors[:2])
        vocab_hint = ", ".join(payload.vocab_candidates[:2])
        history_hint = payload.recent_messages[-1].text if payload.recent_messages else learner
        return CoachReplyResult(
            text=(
                f"As your {payload.role}, I understand you said '{history_hint}'. "
                f"Let's practice with {anchor_hint or vocab_hint or learner}. {follow_up}"
            )
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


def build_primary_chat_provider() -> ChatProvider:
    """按主配置构造文本对话 provider。"""
    return _build_provider(
        provider=settings.text_primary_provider,
        base_url=settings.text_primary_base_url,
        api_key=settings.text_primary_api_key,
        model=settings.text_primary_model,
        timeout_seconds=settings.text_primary_timeout_seconds,
    )


def build_fallback_chat_provider() -> ChatProvider:
    """按回退配置构造文本对话 provider。"""
    return _build_provider(
        provider=settings.text_fallback_provider,
        base_url=settings.text_fallback_base_url,
        api_key=settings.text_fallback_api_key,
        model=settings.text_fallback_model,
        timeout_seconds=settings.text_fallback_timeout_seconds,
    )


def has_real_chat_provider(provider: str) -> bool:
    """判断当前配置是否会走真实文本模型。"""
    return provider.strip().lower() not in {"", "mock"}


def _build_provider(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
) -> ChatProvider:
    """根据运行模式和 provider 名称选择 mock 或真实实现。"""
    normalized = provider.strip().lower()
    if settings.model_runtime_mode.lower() != "live":
        return MockChatProvider()
    if normalized in {"", "mock"}:
        raise ConfigurationError("Live runtime requires at least one real text provider")
    if normalized == "openai_compatible":
        return OpenAICompatibleChatProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    raise ConfigurationError(f"Unsupported text provider: {provider}")


def _build_coach_user_prompt(payload: CoachReplyInput) -> str:
    """把场景、上下文和最近消息整理成单个用户提示词。"""
    recent_messages = [
        f"{message.role}: {message.text}"
        for message in payload.recent_messages[-4:]
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
