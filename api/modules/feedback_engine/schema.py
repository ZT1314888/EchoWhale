from pydantic import BaseModel


class FeedbackInput(BaseModel):
    learner_message: str
    scene: str


class FeedbackResult(BaseModel):
    grammar: str
    more_natural: str
    useful_words: list[str]
