from api.modules.coach_engine.agent import CoachEngineAgent
from api.modules.coach_engine.providers.chat_provider import ChatProvider
from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult
from api.models.message_model import Message


class CoachEngineService:
    def __init__(
        self,
        *,
        primary_provider: ChatProvider | None = None,
        fallback_provider: ChatProvider | None = None,
    ) -> None:
        self.agent = CoachEngineAgent(
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
        )

    def respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
    ) -> CoachReplyResult:
        payload = CoachReplyInput(
            scene=scene,
            role=role,
            learner_message=learner_message,
            visual_anchors=visual_anchors,
            vocab_candidates=vocab_candidates,
            recent_messages=recent_messages,
        )
        return self.agent.run(payload)
