from api.modules.feedback_engine.agent import FeedbackEngineAgent
from api.modules.feedback_engine.schema import FeedbackInput, FeedbackResult


class FeedbackEngineService:
    def __init__(self) -> None:
        self.agent = FeedbackEngineAgent()

    def review(self, learner_message: str, scene: str) -> FeedbackResult:
        payload = FeedbackInput(learner_message=learner_message, scene=scene)
        return self.agent.run(payload)
