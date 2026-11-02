from __future__ import annotations

from api.core.config import settings
from api.integrations.llm.json_utils import parse_llm_json
from api.integrations.llm.resilience import LLMAttempt, run_llm_with_failover
from api.integrations.llm.runtime import (
    TextCompletionProvider,
    provider_slot_from_settings,
    resolve_engine_providers,
)
from api.modules.coach_engine.providers.chat_provider import MockChatProvider
from api.modules.feedback_engine.prompts.feedback_prompts import (
    FEEDBACK_PROMPT,
    build_feedback_user_prompt,
)
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
        # user prompt 装配收敛到 prompts.build_feedback_user_prompt 单一装配点
        # （P0/G8）：live 链路与评测台共用，消除两处契约漂移。
        user_prompt = build_feedback_user_prompt(payload)

        primary, fallback = resolve_engine_providers(
            kind="text",
            primary_slot=provider_slot_from_settings("text", "primary"),
            fallback_slot=provider_slot_from_settings("text", "fallback"),
            build_mock=MockChatProvider,
            build_real=lambda slot: TextCompletionProvider(
                slot,
                json_mode=settings.llm_json_mode_enabled,
                # 反馈输出预算（Finding 10a）：与教练/场景各自独立配额。
                max_tokens=settings.llm_feedback_max_tokens,
            ),
        )

        attempts = [LLMAttempt("text_primary", lambda: _request_feedback(primary, user_prompt))]
        if fallback is not primary:
            attempts.append(
                LLMAttempt("text_fallback", lambda: _request_feedback(fallback, user_prompt))
            )
        return await run_llm_with_failover(
            attempts,
            retries_per_provider=settings.llm_max_retries_per_provider,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
            deadline_seconds=settings.llm_request_deadline_seconds,
        )


async def _request_feedback(provider: TextCompletionProvider, user_prompt: str) -> FeedbackResult:
    """调用文本模型并校验结构化输出；解析失败按可重试的 provider 错误处理。"""
    raw = await provider.complete(system_prompt=FEEDBACK_PROMPT, user_prompt=user_prompt)
    return FeedbackResult.model_validate(parse_llm_json(raw))
