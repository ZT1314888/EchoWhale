from api.modules.feedback_engine.schema import FeedbackInput, FeedbackResult
from api.modules.feedback_engine.tools.correction_tools import normalize_sentence


class FeedbackEngineAgent:
    def run(self, payload: FeedbackInput) -> FeedbackResult:
        improved = normalize_sentence(payload.learner_message)
        useful_words = {
            "restaurant": ["order", "menu", "recommend"],
            "coffee_shop": ["latte", "iced", "size"],
            "office": ["deadline", "update", "priority"],
            "travel": ["ticket", "platform", "direction"],
        }.get(payload.scene, ["conversation", "detail", "response"])

        return FeedbackResult(
            grammar="Your meaning is clear. Add articles and complete sentence endings when possible.",
            more_natural=improved if improved.endswith(".") else f"{improved}.",
            useful_words=useful_words,
        )
