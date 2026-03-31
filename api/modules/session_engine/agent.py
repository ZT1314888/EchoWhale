from uuid import uuid4

from api.db.media_db import get_media
from api.db.session_db import add_message, get_session, save_session
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.coach_engine.service import CoachEngineService
from api.modules.feedback_engine.service import FeedbackEngineService
from api.modules.scene_engine.service import SceneEngineService
from api.modules.session_engine.schema import ReplyInput, StartSessionInput


class SessionEngineAgent:
    def __init__(self) -> None:
        self.scene_engine = SceneEngineService()
        self.coach_engine = CoachEngineService()
        self.feedback_engine = FeedbackEngineService()

    def start(self, payload: StartSessionInput) -> Session:
        media = get_media(payload.media_id)
        analysis = self.scene_engine.analyze(media.filename, media.url)
        session = Session(
            id=uuid4().hex,
            user_id=payload.user_id,
            media_id=media.id,
            scene=analysis.scene,
            role=analysis.role,
            opener=analysis.opener,
            labels=analysis.labels,
            messages=[Message(role="assistant", text=analysis.opener)],
        )
        return save_session(session)

    def reply(self, payload: ReplyInput) -> Session:
        session = get_session(payload.session_id)
        add_message(session.id, Message(role="user", text=payload.learner_message))

        feedback = self.feedback_engine.review(payload.learner_message, session.scene)
        coach_reply = self.coach_engine.respond(
            scene=session.scene,
            role=session.role,
            learner_message=payload.learner_message,
        )

        assistant_message = Message(
            role="assistant",
            text=coach_reply.text,
            feedback=feedback.model_dump(),
        )
        return add_message(session.id, assistant_message)
