from api.common.exceptions import NotFoundError
from api.models.message_model import Message
from api.models.session_model import Session


_sessions: dict[str, Session] = {}


def save_session(session: Session) -> Session:
    _sessions[session.id] = session
    return session


def get_session(session_id: str) -> Session:
    session = _sessions.get(session_id)
    if not session:
        raise NotFoundError(f"Session {session_id} not found")
    return session


def add_message(session_id: str, message: Message) -> Session:
    session = get_session(session_id)
    session.messages.append(message)
    _sessions[session_id] = session
    return session


def list_user_sessions(user_id: str) -> list[Session]:
    return [session for session in _sessions.values() if session.user_id == user_id]
