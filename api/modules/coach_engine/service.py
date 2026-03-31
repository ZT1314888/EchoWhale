from api.modules.coach_engine.agent import CoachEngineAgent
from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult


class CoachEngineService:
    def __init__(self) -> None:
        self.agent = CoachEngineAgent()

    def respond(self, scene: str, role: str, learner_message: str) -> CoachReplyResult:
        payload = CoachReplyInput(
            scene=scene,
            role=role,
            learner_message=learner_message,
        )
        return self.agent.run(payload)
