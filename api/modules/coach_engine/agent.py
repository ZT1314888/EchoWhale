from api.core.config import settings
from api.integrations.llm.base import TextStream
from api.integrations.llm.resilience import LLMAttempt
from api.integrations.llm.resilience import run_llm_with_failover
from api.integrations.llm.runtime import provider_slot_from_settings
from api.integrations.llm.runtime import resolve_engine_providers
from api.integrations.llm.streaming import SingleDeltaTextStream
from api.modules.coach_engine.providers.chat_provider import ChatProvider
from api.modules.coach_engine.providers.chat_provider import MockChatProvider
from api.modules.coach_engine.providers.chat_provider import OpenAICompatibleChatProvider
from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult


class CoachEngineAgent:
    def __init__(
        self,
        primary_provider: ChatProvider | None = None,
        fallback_provider: ChatProvider | None = None,
    ) -> None:
        """初始化主备文本 provider；显式注入优先于配置解析。"""
        if primary_provider is not None:
            self.primary_provider = primary_provider
            self.fallback_provider = fallback_provider or primary_provider
            return

        self.primary_provider, self.fallback_provider = resolve_engine_providers(
            kind="text",
            primary_slot=provider_slot_from_settings("text", "primary"),
            fallback_slot=provider_slot_from_settings("text", "fallback"),
            build_mock=lambda: MockChatProvider(),
            build_real=lambda slot: OpenAICompatibleChatProvider(
                base_url=slot.base_url,
                api_key=slot.api_key,
                model=slot.model,
                timeout_seconds=slot.timeout_seconds,
            ),
        )

    async def run(self, payload: CoachReplyInput) -> CoachReplyResult:
        """优先调用主 provider：瞬时错误带退避重试，仍失败则退回备用 provider。"""
        attempts = [
            LLMAttempt("text_primary", lambda: self.primary_provider.reply(payload))
        ]
        if self.fallback_provider is not self.primary_provider:
            attempts.append(
                LLMAttempt("text_fallback", lambda: self.fallback_provider.reply(payload))
            )
        return await run_llm_with_failover(
            attempts,
            retries_per_provider=settings.llm_max_retries_per_provider,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
            deadline_seconds=settings.llm_request_deadline_seconds,
        )

    async def stream_reply(self, payload: CoachReplyInput) -> TextStream:
        """打开教练回复流：只有"打开"阶段参与重试与主备切换，开流后不再整体重来。"""
        attempts = [
            LLMAttempt(
                "text_primary",
                lambda: self._open_reply_stream(self.primary_provider, payload),
            )
        ]
        if self.fallback_provider is not self.primary_provider:
            attempts.append(
                LLMAttempt(
                    "text_fallback",
                    lambda: self._open_reply_stream(self.fallback_provider, payload),
                )
            )
        return await run_llm_with_failover(
            attempts,
            retries_per_provider=settings.llm_max_retries_per_provider,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
            deadline_seconds=settings.llm_request_deadline_seconds,
        )

    async def _open_reply_stream(
        self,
        provider: ChatProvider,
        payload: CoachReplyInput,
    ) -> TextStream:
        """provider 支持流式则原样打开，否则退化为整段单 delta。"""
        opener = getattr(provider, "open_reply_stream", None)
        if opener is None:
            reply = await provider.reply(payload)
            return SingleDeltaTextStream(reply.text)
        return await opener(payload)
