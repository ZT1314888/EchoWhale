from __future__ import annotations

import json

from api.common.exceptions import ModelProviderError
from api.core.config import settings
from api.integrations.llm.openai import OpenAICompatibleClient
from api.modules.feedback_engine.prompts.feedback_prompts import FEEDBACK_PROMPT
from api.modules.feedback_engine.schema import FeedbackInput, FeedbackResult
from api.modules.feedback_engine.tools.correction_tools import normalize_sentence


class FeedbackEngineAgent:
    def run(self, payload: FeedbackInput) -> FeedbackResult:
        if _should_use_live_feedback():
            return self._run_live(payload)

        improved = normalize_sentence(payload.learner_message)
        useful_words = payload.vocab_candidates or {
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

    def _run_live(self, payload: FeedbackInput) -> FeedbackResult:
        user_prompt = "\n".join(
            [
                f"Scene: {payload.scene}",
                f"Vocab candidates: {', '.join(payload.vocab_candidates) or 'none'}",
                f"Learner message: {payload.learner_message}",
                "Return strict JSON with keys: grammar, more_natural, useful_words.",
                "useful_words must be an array of short English words or phrases.",
            ]
        )

        primary_client = OpenAICompatibleClient(
            base_url=settings.text_primary_base_url,
            api_key=settings.text_primary_api_key,
            model=settings.text_primary_model,
            timeout_seconds=settings.text_primary_timeout_seconds,
        )

        try:
            raw = primary_client.complete_text(
                system_prompt=FEEDBACK_PROMPT,
                user_prompt=user_prompt,
            )
            return FeedbackResult.model_validate(_load_json(raw))
        except Exception:
            fallback_client = OpenAICompatibleClient(
                base_url=settings.text_fallback_base_url,
                api_key=settings.text_fallback_api_key,
                model=settings.text_fallback_model,
                timeout_seconds=settings.text_fallback_timeout_seconds,
            )
            try:
                raw = fallback_client.complete_text(
                    system_prompt=FEEDBACK_PROMPT,
                    user_prompt=user_prompt,
                )
                return FeedbackResult.model_validate(_load_json(raw))
            except Exception as exc:  # pragma: no cover - live provider path
                raise ModelProviderError("Feedback provider failed to generate review") from exc


def _load_json(raw: str) -> dict[str, object]:
    normalized = raw.strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.lower().startswith("json"):
            normalized = normalized[4:].strip()
    return json.loads(normalized)


def _should_use_live_feedback() -> bool:
    if settings.model_runtime_mode.lower() != "live":
        return False

    return any(
        provider.strip().lower() not in {"", "mock"}
        for provider in (
            settings.text_primary_provider,
            settings.text_fallback_provider,
        )
    )
