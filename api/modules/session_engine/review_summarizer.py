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
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.prompts.review_prompts import REVIEW_PROMPT
from api.modules.session_engine.review_builder import ReviewCopy


class ReviewSummarizerAgent:
    """把单轮反馈汇总成中文复盘文案的 LLM agent（审计 Finding 20）。

    live 专用增强分支：mock 模式下编排层直接短路、不装配调用；
    live 未配 provider 时由 failover 骨架上抛 ConfigurationError，
    编排层捕获后降级模板复盘。provider 接线复用反馈引擎模式，
    用量 sink 在 TextCompletionProvider 构造期默认注入 llm_usage 账本。
    """

    async def summarize(
        self,
        *,
        scene: str,
        role: str,
        learner_message: str,
        feedback: FeedbackResult,
    ) -> ReviewCopy:
        """按主备顺序轮询文本模型，直到成功产出结构化复盘文案。"""
        user_prompt = "\n".join(
            [
                f"Scene: {scene}",
                f"Role: {role}",
                f"Learner message: {learner_message}",
                f"Feedback JSON: {feedback.model_dump_json()}",
                # 输出契约以系统提示词为准，这里只给数据不重复键清单。
                "Return strict JSON following the output contract in the system prompt.",
            ]
        )

        primary, fallback = resolve_engine_providers(
            kind="text",
            primary_slot=provider_slot_from_settings("text", "primary"),
            fallback_slot=provider_slot_from_settings("text", "fallback"),
            build_mock=MockChatProvider,
            build_real=lambda slot: TextCompletionProvider(
                slot,
                json_mode=settings.llm_json_mode_enabled,
                # 复盘输出是短中文文案，预算独立于教练/反馈（Finding 10a 同族）。
                max_tokens=settings.llm_review_max_tokens,
            ),
        )

        attempts = [LLMAttempt("text_primary", lambda: _request_copy(primary, user_prompt))]
        if fallback is not primary:
            attempts.append(
                LLMAttempt("text_fallback", lambda: _request_copy(fallback, user_prompt))
            )
        return await run_llm_with_failover(
            attempts,
            retries_per_provider=settings.llm_max_retries_per_provider,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
            deadline_seconds=settings.llm_request_deadline_seconds,
        )


async def _request_copy(provider: TextCompletionProvider, user_prompt: str) -> ReviewCopy:
    """调用文本模型并校验复盘文案结构；解析失败按可重试的 provider 错误处理。"""
    raw = await provider.complete(system_prompt=REVIEW_PROMPT, user_prompt=user_prompt)
    return ReviewCopy.model_validate(parse_llm_json(raw))
