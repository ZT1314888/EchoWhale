from pydantic import BaseModel


class CoachReplyInput(BaseModel):
    scene: str
    role: str
    learner_message: str


class CoachReplyResult(BaseModel):
    text: str
