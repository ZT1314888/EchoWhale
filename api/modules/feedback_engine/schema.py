from pydantic import BaseModel, Field


class FeedbackInput(BaseModel):
    learner_message: str
    scene: str
    vocab_candidates: list[str] = Field(default_factory=list)


class FeedbackResult(BaseModel):
    grammar: str
    more_natural: str
    useful_words: list[str]
