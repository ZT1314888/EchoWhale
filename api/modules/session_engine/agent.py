from uuid import uuid4

from api.common.enums import MediaUploadStatus
from api.common.exceptions import InvalidStateError
from api.core.config import settings
from api.db.media_db import MediaLookup, build_media_repository
from api.db.session_db import SessionRepository, build_session_repository
from api.integrations.storage.r2 import R2StorageService
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.coach_engine.service import CoachEngineService
from api.modules.feedback_engine.service import FeedbackEngineService
from api.modules.scene_engine.service import SceneEngineService
from api.modules.session_engine.review_builder import build_session_review
from api.modules.session_engine.schema import ReplyInput, StartSessionInput


class SessionEngineAgent:
    def __init__(
        self,
        media_lookup: MediaLookup | None = None,
        session_repository: SessionRepository | None = None,
        read_url_signer: R2StorageService | None = None,
    ) -> None:
        self.media_lookup = media_lookup or build_media_repository()
        self.session_repository = session_repository or build_session_repository()
        self.read_url_signer = read_url_signer or R2StorageService()
        self.scene_engine = SceneEngineService()
        self.coach_engine = CoachEngineService()
        self.feedback_engine = FeedbackEngineService()

    def start(self, payload: StartSessionInput) -> Session:
        media = self.media_lookup.get_media(payload.media_id)
        if media.upload_status != MediaUploadStatus.uploaded:
            raise InvalidStateError(f"Media {media.id} is not uploaded")

        signed_read_url, _ = self.read_url_signer.create_signed_read_url(
            media.storage_key,
            expires_in=settings.r2_signed_url_ttl_seconds,
        )
        analysis = self.scene_engine.analyze(media.filename, signed_read_url)
        session = Session(
            id=f"sess_{uuid4().hex[:12]}",
            user_id=payload.user_id,
            media_id=media.id,
            scene=analysis.scene,
            role=analysis.role,
            opener=analysis.opener,
            labels=analysis.labels,
            messages=[Message(role="assistant", text=analysis.opener)],
        )
        return self.session_repository.save_session(session)

    def get(self, session_id: str) -> Session:
        return self.session_repository.get_session(session_id)

    def reply(self, payload: ReplyInput) -> Session:
        session = self.session_repository.get_session(payload.session_id)
        feedback = self.feedback_engine.review(payload.learner_message, session.scene)
        coach_reply = self.coach_engine.respond(
            scene=session.scene,
            role=session.role,
            learner_message=payload.learner_message,
        )
        learner_message = Message(role="user", text=payload.learner_message)

        assistant_message = Message(
            role="assistant",
            text=coach_reply.text,
            feedback=feedback.model_dump(),
        )
        updated_session = session.model_copy(
            update={"messages": [*session.messages, learner_message, assistant_message]}
        )
        review = build_session_review(updated_session, feedback)
        return self.session_repository.save_reply_turn(
            session.id,
            learner_message,
            assistant_message,
            review,
        )

    def get_review(self, session_id: str):
        return self.session_repository.get_session_review(session_id)

    def list_history_sessions(self, user_id: str) -> list[Session]:
        return self.session_repository.list_user_sessions(user_id)
