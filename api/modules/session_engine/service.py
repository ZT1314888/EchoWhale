from api.models.session_model import Session
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.schema import ReplyInput, StartSessionInput


class SessionEngineService:
    def __init__(self) -> None:
        self.agent = SessionEngineAgent()

    def start_session(self, user_id: str, media_id: str) -> Session:
        payload = StartSessionInput(user_id=user_id, media_id=media_id)
        return self.agent.start(payload)

    def reply_to_session(self, session_id: str, learner_message: str) -> Session:
        payload = ReplyInput(session_id=session_id, learner_message=learner_message)
        return self.agent.reply(payload)
