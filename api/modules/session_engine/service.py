from __future__ import annotations

from api.common.exceptions import NotFoundError
from api.models.session_model import Session
from api.db.media_db import MediaLookup
from api.db.session_db import SessionRepository
from api.integrations.storage.r2 import R2StorageService
from api.models.review_model import SessionReview
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.schema import (
    ReplyInput,
    StartSessionInput,
    VoiceBootstrapResult,
    VoiceCompleteInput,
    VoiceCompleteResult,
)


class SessionEngineService:
    def __init__(
        self,
        media_lookup: MediaLookup | None = None,
        session_repository: SessionRepository | None = None,
        read_url_signer: R2StorageService | None = None,
    ) -> None:
        self.agent = SessionEngineAgent(
            media_lookup=media_lookup,
            session_repository=session_repository,
            read_url_signer=read_url_signer,
        )

    def start_session(
        self,
        user_id: str,
        media_id: str | None = None,
        sample_scene_id: str | None = None,
    ) -> Session:
        payload = StartSessionInput(
            user_id=user_id,
            media_id=media_id,
            sample_scene_id=sample_scene_id,
        )
        return self.agent.start(payload)

    def get_session(self, session_id: str, owner_id: str | None = None) -> Session:
        session = self.agent.get(session_id)
        return self._ensure_owner(session, owner_id)

    def reply_to_session(
        self,
        session_id: str,
        learner_message: str,
        owner_id: str | None = None,
    ) -> Session:
        self._ensure_owner(self.agent.get(session_id), owner_id)
        payload = ReplyInput(session_id=session_id, learner_message=learner_message)
        return self.agent.reply(payload)

    def get_session_review(self, session_id: str, owner_id: str | None = None) -> SessionReview:
        self._ensure_owner(self.agent.get(session_id), owner_id)
        return self.agent.get_review(session_id)

    def list_history_sessions(self, user_id: str) -> list[Session]:
        return self.agent.list_history_sessions(user_id)

    def get_history_session_detail(self, user_id: str, session_id: str) -> tuple[Session, SessionReview]:
        session = self._ensure_owner(self.agent.get(session_id), user_id)
        return (session, self.agent.get_review(session_id))

    def bootstrap_voice_session(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> VoiceBootstrapResult:
        self._ensure_owner(self.agent.get(session_id), owner_id)
        return self.agent.bootstrap_voice_session(session_id)

    def complete_voice_session(
        self,
        session_id: str,
        conversation,
        termination_reason: str,
        client_diagnostics: dict[str, object] | None = None,
        owner_id: str | None = None,
    ) -> VoiceCompleteResult:
        self._ensure_owner(self.agent.get(session_id), owner_id)
        payload = VoiceCompleteInput(
            session_id=session_id,
            conversation=conversation,
            termination_reason=termination_reason,
            client_diagnostics=client_diagnostics or {},
        )
        return self.agent.complete_voice_session(payload)

    def _ensure_owner(self, session: Session, owner_id: str | None) -> Session:
        if owner_id is None or session.user_id == owner_id:
            return session
        raise NotFoundError(f"Session {session.id} not found")
