from api.modules.coach_engine.providers.chat_provider import MockChatProvider
from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult


class CoachEngineAgent:
    def __init__(self) -> None:
        self.provider = MockChatProvider()

    def run(self, payload: CoachReplyInput) -> CoachReplyResult:
        return self.provider.reply(payload)
