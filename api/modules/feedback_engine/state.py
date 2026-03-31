from pydantic import BaseModel


class FeedbackState(BaseModel):
    latest_feedback: str | None = None
