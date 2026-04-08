import inspect
from datetime import datetime, timezone
from uuid import uuid4

from api.common.enums import MediaUploadStatus
from api.common.exceptions import EchoWhaleError
from api.common.exceptions import InvalidStateError
from api.common.exceptions import SceneAnalysisUnavailableError
from api.common.exceptions import UnsupportedSceneImageError
from api.common.exceptions import ValidationError as AppValidationError
from api.core.config import settings
from api.db.media_db import MediaLookup, build_media_repository
from api.db.session_db import SessionRepository, build_session_repository
from api.integrations.deepgram import DeepgramSettingsBuilder
from api.integrations.deepgram import DeepgramTokenIssuer
from api.integrations.storage.r2 import R2StorageService
from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.runtime_model import SessionEvent
from api.models.runtime_model import VoiceSessionFact
from api.models.session_model import Session
from api.modules.coach_engine.service import CoachEngineService
from api.modules.feedback_engine.service import FeedbackEngineService
from api.modules.scene_engine.service import SceneEngineService
from api.modules.session_engine.review_builder import build_session_review
from api.modules.session_engine.sample_presets import get_sample_session_preset
from api.modules.session_engine.schema import (
    ReplyInput,
    StartSessionInput,
    VoiceBootstrapResult,
    VoiceCompleteInput,
    VoiceCompleteResult,
)


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
        self.voice_token_issuer = DeepgramTokenIssuer()
        self.voice_settings_builder = DeepgramSettingsBuilder()

    def start(self, payload: StartSessionInput) -> Session:
        if payload.sample_scene_id is not None:
            preset = get_sample_session_preset(payload.sample_scene_id)
            session = Session(
                id=f"sess_{uuid4().hex[:12]}",
                user_id=payload.user_id,
                media_id=None,
                scene=preset.scene,
                role=preset.role,
                opener=preset.opener,
                visual_anchors=list(preset.visual_anchors),
                vocab_candidates=list(preset.vocab_candidates),
                messages=[Message(role="assistant", text=preset.opener)],
            )
            return self.session_repository.save_session(session)

        assert payload.media_id is not None
        media = self.media_lookup.get_media(payload.media_id)
        if media.upload_status != MediaUploadStatus.uploaded:
            raise InvalidStateError(f"Media {media.id} is not uploaded")

        signed_read_url, _ = self.read_url_signer.create_signed_read_url(
            media.storage_key,
            expires_in=settings.r2_signed_url_ttl_seconds,
        )
        try:
            analysis = self.scene_engine.analyze(media.filename, signed_read_url)
        except UnsupportedSceneImageError:
            raise
        except EchoWhaleError as exc:
            raise SceneAnalysisUnavailableError() from exc
        session = Session(
            id=f"sess_{uuid4().hex[:12]}",
            user_id=payload.user_id,
            media_id=media.id,
            scene=analysis.scene,
            role=analysis.role,
            opener=analysis.opener,
            visual_anchors=analysis.visual_anchors,
            vocab_candidates=analysis.vocab_candidates,
            messages=[Message(role="assistant", text=analysis.opener)],
        )
        return self.session_repository.save_session(session)

    def get(self, session_id: str) -> Session:
        return self.session_repository.get_session(session_id)

    def get_session_head(self, session_id: str) -> Session:
        return self.session_repository.get_session_head(session_id)

    def reply(self, payload: ReplyInput) -> Session:
        session = self.session_repository.get_session(payload.session_id)
        feedback = self._review_with_context(
            learner_message=payload.learner_message,
            scene=session.scene,
            vocab_candidates=session.vocab_candidates,
        )
        coach_reply = self._respond_with_context(
            scene=session.scene,
            role=session.role,
            learner_message=payload.learner_message,
            visual_anchors=session.visual_anchors,
            vocab_candidates=session.vocab_candidates,
            recent_messages=list(session.messages),
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

    def list_history_sessions_page(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Session], bool, str | None]:
        cursor_value = _decode_history_cursor(cursor)
        sessions, has_more, next_cursor_value = self.session_repository.list_user_sessions_page(
            user_id,
            limit=limit,
            cursor=cursor_value,
        )
        next_cursor = _encode_history_cursor(next_cursor_value) if next_cursor_value else None
        return (sessions, has_more, next_cursor)

    def list_history_reviews(self, session_ids: list[str]) -> dict[str, SessionReview]:
        if not session_ids:
            return {}
        return self.session_repository.list_session_reviews_by_ids(session_ids)

    def get_history_session_overview(self, session_id: str) -> tuple[Session, SessionReview, int]:
        session = self.get_session_head(session_id)
        review = self.get_review(session_id)
        total_messages = self.session_repository.count_session_messages(session_id)
        return (session, review, total_messages)

    def list_history_session_messages_page(
        self,
        session_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Message], bool, str | None]:
        return self.session_repository.list_session_messages_page(
            session_id,
            limit=limit,
            cursor=cursor,
        )

    def bootstrap_voice_session(self, session_id: str) -> VoiceBootstrapResult:
        session = self.session_repository.get_session(session_id)
        token, expires_in = self.voice_token_issuer.issue_token(
            settings.deepgram_agent_token_ttl_seconds
        )
        bootstrap = VoiceBootstrapResult(
            session_id=session.id,
            deepgram_access_token=token,
            expires_in=expires_in,
            deepgram_ws_url=settings.deepgram_agent_base_url,
            agent_settings=self.voice_settings_builder.build(session),
            session=session,
        )
        self.session_repository.save_voice_session_fact(
            VoiceSessionFact(
                session_id=session.id,
                status="active",
                transcript_turn_count=len(session.messages),
            )
        )
        self.session_repository.save_session_event(
            SessionEvent(
                session_id=session.id,
                event_type="voice_bootstrapped",
                stage="voice_active",
                payload={
                    "expires_in": expires_in,
                    "output_sample_rate": settings.deepgram_agent_output_sample_rate,
                },
            )
        )
        return bootstrap

    def complete_voice_session(self, payload: VoiceCompleteInput) -> VoiceCompleteResult:
        session = self.session_repository.get_session(payload.session_id)
        messages = _build_voice_messages(session, payload)
        updated_session = session.model_copy(
            update={
                "messages": messages,
            }
        )
        last_learner_message = _find_latest_user_content(payload)
        if last_learner_message is None:
            raise AppValidationError("Validation error")
        feedback = self._review_with_context(
            learner_message=last_learner_message,
            scene=updated_session.scene,
            vocab_candidates=updated_session.vocab_candidates,
        )
        review = build_session_review(updated_session, feedback)
        existing_voice_fact = self.session_repository.get_latest_voice_session_fact(payload.session_id)
        voice_fact = VoiceSessionFact(
            session_id=payload.session_id,
            status="completed",
            termination_reason=payload.termination_reason,
            transcript_turn_count=len(payload.conversation),
            client_diagnostics=dict(payload.client_diagnostics),
            started_at=(
                existing_voice_fact.started_at
                if existing_voice_fact is not None
                else updated_session.created_at
            ),
            completed_at=review.updated_at,
            updated_at=review.updated_at,
        )
        events = [
            SessionEvent(
                session_id=payload.session_id,
                event_type="voice_finalized",
                stage="review_ready",
                payload={
                    "termination_reason": payload.termination_reason,
                    "conversation_turn_count": len(payload.conversation),
                    "client_diagnostics": dict(payload.client_diagnostics),
                },
                created_at=review.updated_at,
            ),
            SessionEvent(
                session_id=payload.session_id,
                event_type="review_built",
                stage="review_ready",
                payload={"review_title": review.title},
                created_at=review.updated_at,
            ),
        ]
        stored_session, stored_review = self.session_repository.finalize_voice_session(
            session=updated_session,
            review=review,
            voice_fact=voice_fact,
            events=events,
        )
        return VoiceCompleteResult(session=stored_session, review=stored_review)

    def _review_with_context(
        self,
        *,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
    ):
        parameters = inspect.signature(self.feedback_engine.review).parameters
        if "vocab_candidates" in parameters:
            return self.feedback_engine.review(learner_message, scene, vocab_candidates)
        if "labels" in parameters:
            return self.feedback_engine.review(learner_message, scene, vocab_candidates)
        return self.feedback_engine.review(learner_message, scene)

    def _respond_with_context(
        self,
        *,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
    ):
        parameters = inspect.signature(self.coach_engine.respond).parameters
        if "visual_anchors" in parameters and "vocab_candidates" in parameters:
            return self.coach_engine.respond(
                scene=scene,
                role=role,
                learner_message=learner_message,
                visual_anchors=visual_anchors,
                vocab_candidates=vocab_candidates,
                recent_messages=recent_messages,
            )
        if "visual_anchors" in parameters:
            return self.coach_engine.respond(
                scene=scene,
                role=role,
                learner_message=learner_message,
                visual_anchors=visual_anchors,
                recent_messages=recent_messages,
            )
        if "labels" in parameters or "recent_messages" in parameters:
            return self.coach_engine.respond(
                scene=scene,
                role=role,
                learner_message=learner_message,
                labels=visual_anchors,
                recent_messages=recent_messages,
            )
        return self.coach_engine.respond(scene, role, learner_message)


def _build_voice_messages(session: Session, payload: VoiceCompleteInput) -> list[Message]:
    transcript: list[Message] = []
    for index, turn in enumerate(payload.conversation):
        if (
            index == 0
            and turn.role == "assistant"
            and session.messages
            and session.messages[0].role == "assistant"
            and turn.content == session.messages[0].text
        ):
            transcript.append(session.messages[0])
            continue
        transcript.append(
            Message(
                role=turn.role,
                text=turn.content,
            )
        )

    if not session.messages:
        return transcript

    remainder = list(transcript)
    if remainder and _message_signature(remainder[0]) == _message_signature(session.messages[0]):
        remainder = remainder[1:]

    overlap = _find_tail_overlap(existing=session.messages, incoming=remainder)
    return [*session.messages, *remainder[overlap:]]


def _find_latest_user_content(payload: VoiceCompleteInput) -> str | None:
    for turn in reversed(payload.conversation):
        if turn.role == "user":
            return turn.content
    return None


def _find_tail_overlap(*, existing: list[Message], incoming: list[Message]) -> int:
    max_overlap = min(len(existing), len(incoming))
    for size in range(max_overlap, 0, -1):
        existing_tail = existing[-size:]
        incoming_head = incoming[:size]
        if all(
            _message_signature(left) == _message_signature(right)
            for left, right in zip(existing_tail, incoming_head, strict=False)
        ):
            return size
    return 0


def _message_signature(message: Message) -> tuple[str, str]:
    return (message.role, message.text)


def _encode_history_cursor(value: tuple[datetime, str]) -> str:
    updated_at, session_id = value
    normalized = updated_at.astimezone(timezone.utc)
    return f"{normalized.isoformat()}|{session_id}"


def _decode_history_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if cursor is None:
        return None
    timestamp, _, session_id = cursor.partition("|")
    if not timestamp or not session_id:
        raise AppValidationError("Validation error")
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise AppValidationError("Validation error") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed, session_id)
