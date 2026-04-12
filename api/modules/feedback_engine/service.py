from api.modules.feedback_engine.agent import FeedbackEngineAgent
from api.modules.feedback_engine.schema import FeedbackInput, FeedbackResult


class FeedbackEngineService:
    def __init__(self) -> None:
        """装配反馈 agent，对外提供稳定的评语入口。"""
        self.agent = FeedbackEngineAgent()

    async def review(
        self,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
    ) -> FeedbackResult:
        """把学习者输入包装成反馈 payload 并委托给 agent。"""
        payload = FeedbackInput(
            learner_message=learner_message,
            scene=scene,
            vocab_candidates=vocab_candidates,
        )
        return await self.agent.run(payload)
