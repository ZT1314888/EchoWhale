from __future__ import annotations

import json

from api.common.exceptions import ConfigurationError
from api.common.exceptions import ModelProviderError
from api.core.config import settings
from api.integrations.llm.openai import OpenAICompatibleClient
from api.modules.feedback_engine.prompts.feedback_prompts import FEEDBACK_PROMPT
from api.modules.feedback_engine.schema import FeedbackInput, FeedbackResult
from api.modules.feedback_engine.tools.correction_tools import normalize_sentence


class FeedbackEngineAgent:
    async def run(self, payload: FeedbackInput) -> FeedbackResult:
        """按运行模式选择 mock 反馈或远端模型反馈。"""
        if settings.model_runtime_mode.lower() == "live":
            return await self._run_live(payload)

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

    async def _run_live(
        self,
        payload: FeedbackInput,
    ) -> FeedbackResult:
        """按主备顺序轮询文本模型，直到成功产出结构化反馈。"""
        user_prompt = "\n".join(
            [
                f"Scene: {payload.scene}",
                f"Vocab candidates: {', '.join(payload.vocab_candidates) or 'none'}",
                f"Learner message: {payload.learner_message}",
                "Return strict JSON with keys: grammar, more_natural, useful_words.",
                "useful_words must be an array of short English words or phrases.",
            ]
        )

        active_clients = _build_live_feedback_clients()
        if not active_clients:
            raise ConfigurationError("Live runtime requires at least one real text provider")

        last_error: Exception | None = None
        for client in active_clients:
            try:
                raw = await client.async_complete_text(
                    system_prompt=FEEDBACK_PROMPT,
                    user_prompt=user_prompt,
                )
                return FeedbackResult.model_validate(_load_json(raw))
            except Exception as exc:
                last_error = exc

        raise ModelProviderError("Feedback provider failed to generate review") from last_error


def _load_json(raw: str) -> dict[str, object]:
    """兼容模型把 JSON 包在 Markdown 代码块中的输出。"""
    normalized = raw.strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.lower().startswith("json"):
            normalized = normalized[4:].strip()
    return json.loads(normalized)


def _build_live_feedback_clients() -> list[OpenAICompatibleClient]:
    """按主备配置构建 live 模式可尝试的文本模型客户端列表。"""
    if settings.model_runtime_mode.lower() != "live":
        return []

    clients: list[OpenAICompatibleClient] = []
    for provider, base_url, api_key, model, timeout_seconds in (
        (
            settings.text_primary_provider,
            settings.text_primary_base_url,
            settings.text_primary_api_key,
            settings.text_primary_model,
            settings.text_primary_timeout_seconds,
        ),
        (
            settings.text_fallback_provider,
            settings.text_fallback_base_url,
            settings.text_fallback_api_key,
            settings.text_fallback_model,
            settings.text_fallback_timeout_seconds,
        )
    ):
        if provider.strip().lower() in {"", "mock"}:
            continue
        clients.append(
            OpenAICompatibleClient(
                base_url=base_url,
                api_key=api_key,
                model=model,
                timeout_seconds=timeout_seconds,
            )
        )

    if not clients:
        raise ConfigurationError("Live runtime requires at least one real text provider")
    return clients
