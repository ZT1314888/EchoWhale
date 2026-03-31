from pydantic import BaseModel


class SessionEngineState(BaseModel):
    active_session_id: str | None = None
