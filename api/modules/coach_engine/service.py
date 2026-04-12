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
        """装配对话 agent，对外暴露更稳定的服务层接口。"""
        self.agent = CoachEngineAgent(
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
        )

    async def respond(
        self,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
    ) -> CoachReplyResult:
        """把会话上下文组装成 payload，并转交给对话 agent。"""
        payload = CoachReplyInput(
            scene=scene,
            role=role,
            learner_message=learner_message,
            visual_anchors=visual_anchors,
            vocab_candidates=vocab_candidates,
            recent_messages=recent_messages,
        )
        return await self.agent.run(payload)
