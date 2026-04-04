from pydantic import BaseModel, field_validator


class StartSessionInput(BaseModel):
    user_id: str
    media_id: str


class LearnerMessagePayload(BaseModel):
    learner_message: str

    @field_validator("learner_message")
    @classmethod
    def normalize_learner_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Learner message cannot be empty")
        return normalized


class ReplyInput(LearnerMessagePayload):
    session_id: str
