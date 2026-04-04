from datetime import datetime, timezone

from pydantic import BaseModel, Field


class FeedbackMetric(BaseModel):
    title: str
    body: str


class UsefulWordsMetric(BaseModel):
    title: str
    words: list[str] = Field(default_factory=list)
    body: str


class PracticeFeedback(BaseModel):
    grammar: FeedbackMetric
    more_natural: FeedbackMetric
    useful_words: UsefulWordsMetric
    next_step: FeedbackMetric


class SessionReview(BaseModel):
    session_id: str
    title: str
    highlight: str
    next_try: str
    feedback: PracticeFeedback
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
