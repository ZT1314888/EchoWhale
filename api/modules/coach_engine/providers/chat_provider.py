from api.modules.coach_engine.schema import CoachReplyInput, CoachReplyResult
from api.modules.coach_engine.tools.dialogue_tools import build_follow_up


class MockChatProvider:
    def reply(self, payload: CoachReplyInput) -> CoachReplyResult:
        learner = payload.learner_message.strip() or "that"
        follow_up = build_follow_up(payload.scene)
        return CoachReplyResult(
            text=f"As your {payload.role}, I understand you said '{learner}'. {follow_up}"
        )
