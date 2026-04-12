from api.common.exceptions import EchoWhaleError
from api.common.exceptions import ConfigurationError
from api.modules.coach_engine.providers.chat_provider import ChatProvider
from api.modules.coach_engine.providers.chat_provider import build_fallback_chat_provider
from api.modules.coach_engine.providers.chat_provider import build_primary_chat_provider
from api.modules.coach_engine.providers.chat_provider import has_real_chat_provider
from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult
from api.core.config import settings


class CoachEngineAgent:
    def __init__(
        self,
        primary_provider: ChatProvider | None = None,
        fallback_provider: ChatProvider | None = None,
    ) -> None:
        """初始化主备文本 provider，并处理 live/mock 模式分流。"""
        if primary_provider is not None:
            self.primary_provider = primary_provider
            self.fallback_provider = fallback_provider or primary_provider
            return

        if settings.model_runtime_mode.lower() == "live":
            has_primary = has_real_chat_provider(settings.text_primary_provider)
            has_fallback = has_real_chat_provider(settings.text_fallback_provider)
            if not has_primary and not has_fallback:
                raise ConfigurationError("Live runtime requires at least one real text provider")
            if has_primary:
                self.primary_provider = build_primary_chat_provider()
                self.fallback_provider = (
                    fallback_provider
                    or build_fallback_chat_provider()
                    if has_fallback
                    else self.primary_provider
                )
                return
            resolved_fallback = fallback_provider or build_fallback_chat_provider()
            self.primary_provider = resolved_fallback
            self.fallback_provider = resolved_fallback
            return

        self.primary_provider = build_primary_chat_provider()
        self.fallback_provider = fallback_provider or build_fallback_chat_provider()

    async def run(self, payload: CoachReplyInput) -> CoachReplyResult:
        """优先调用主 provider，失败时按配置退回备用 provider。"""
        try:
            return await self.primary_provider.reply(payload)
        except EchoWhaleError:
            if self.fallback_provider is self.primary_provider:
                raise
            return await self.fallback_provider.reply(payload)
