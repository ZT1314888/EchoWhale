from pydantic import BaseModel


class StartSessionInput(BaseModel):
    user_id: str
    media_id: str


class ReplyInput(BaseModel):
    session_id: str
    learner_message: str
