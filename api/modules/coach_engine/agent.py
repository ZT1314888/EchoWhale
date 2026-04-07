from api.common.exceptions import EchoWhaleError
from api.modules.coach_engine.providers.chat_provider import ChatProvider
from api.modules.coach_engine.providers.chat_provider import build_fallback_chat_provider
from api.modules.coach_engine.providers.chat_provider import build_primary_chat_provider
from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult


class CoachEngineAgent:
    def __init__(
        self,
        primary_provider: ChatProvider | None = None,
        fallback_provider: ChatProvider | None = None,
    ) -> None:
        self.primary_provider = primary_provider or build_primary_chat_provider()
        self.fallback_provider = fallback_provider or build_fallback_chat_provider()

    def run(self, payload: CoachReplyInput) -> CoachReplyResult:
        try:
            return self.primary_provider.reply(payload)
        except EchoWhaleError:
            if self.fallback_provider is self.primary_provider:
                raise
            return self.fallback_provider.reply(payload)
