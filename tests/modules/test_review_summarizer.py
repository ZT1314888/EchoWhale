"""ReviewSummarizerAgent 的 fake client 直测：解析、failover 与预算/账本接线；
ReviewCopy 生产截断护栏（eval_prompt_fixes 批次 design 2.3）的截断语义单测。"""

from __future__ import annotations

import json
import logging

import pytest
from pydantic import ValidationError

from api.common.exceptions import ModelProviderError
from api.core.config import settings
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.review_builder import ReviewCopy
from api.modules.session_engine.review_summarizer import ReviewSummarizerAgent

_VALID_COPY = {
    "scene_title": "咖啡店柜台点单",
    "role_label": "店员对话",
    "highlight": "你清楚地表达了自己的需求。",
    "next_try": "下一轮试着补一句口味或杯型细节。",
    "next_step": "把 useful_words 里的词带进下一轮回答。",
}


def _configure_live_text_providers(monkeypatch) -> None:
    """固定 live 模式与主备槽位，并压紧重试参数让失败路径测试快速确定。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "text_primary_provider", "openai_compatible")
    monkeypatch.setattr(settings, "text_primary_base_url", "https://primary.test")
    monkeypatch.setattr(settings, "text_primary_api_key", "primary-key")
    monkeypatch.setattr(settings, "text_primary_model", "primary-model")
    monkeypatch.setattr(settings, "text_fallback_provider", "openai_compatible")
    monkeypatch.setattr(settings, "text_fallback_base_url", "https://fallback.test")
    monkeypatch.setattr(settings, "text_fallback_api_key", "fallback-key")
    monkeypatch.setattr(settings, "text_fallback_model", "fallback-model")
    monkeypatch.setattr(settings, "llm_max_retries_per_provider", 1)
    monkeypatch.setattr(settings, "llm_retry_backoff_seconds", 0.0)


def _feedback() -> FeedbackResult:
    return FeedbackResult(
        grammar="Your meaning is clear.",
        more_natural="Could I get an iced latte, please?",
        useful_words=["latte"],
    )


def _make_fake_client(monkeypatch, respond) -> list:
    """注入一个把 respond 绑定进 async_complete_text 的假客户端，返回构造实例列表。"""
    constructed: list = []

    class FakeOpenAICompatibleClient:
        def __init__(
            self,
            *,
            base_url: str,
            api_key: str,
            model: str,
            timeout_seconds: int,
            json_mode: bool = False,
            stream_include_usage: bool = False,
            max_tokens: int | None = None,
            usage_sink=None,
        ) -> None:
            self.base_url = base_url
            self.max_tokens = max_tokens
            self.usage_sink = usage_sink
            self.calls = 0
            constructed.append(self)

        async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
            self.calls += 1
            return respond(self, system_prompt=system_prompt, user_prompt=user_prompt)

    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient", FakeOpenAICompatibleClient
    )
    return constructed


def _summarize():
    return ReviewSummarizerAgent().summarize(
        scene="coffee_shop",
        role="barista",
        learner_message="I want a latte",
        feedback=_feedback(),
    )


@pytest.mark.anyio
async def test_summarize_parses_valid_json_into_review_copy(monkeypatch) -> None:
    # 固定 live 槽位：mock 模式下 resolve_engine_providers 会构造无 complete 的
    # MockChatProvider，测试结果不应随 ambient .env 的运行模式漂移。
    _configure_live_text_providers(monkeypatch)
    _make_fake_client(monkeypatch, lambda client, **_: json.dumps(_VALID_COPY))

    copy = await _summarize()

    assert isinstance(copy, ReviewCopy)
    assert copy.scene_title == "咖啡店柜台点单"
    assert copy.role_label == "店员对话"
    assert copy.highlight == "你清楚地表达了自己的需求。"
    assert copy.next_try == "下一轮试着补一句口味或杯型细节。"
    assert copy.next_step == "把 useful_words 里的词带进下一轮回答。"


@pytest.mark.anyio
async def test_summarize_user_prompt_carries_scene_role_and_feedback_json(monkeypatch) -> None:
    # 同上：固定 live 槽位，消除对 ambient MODEL_RUNTIME_MODE 的依赖。
    _configure_live_text_providers(monkeypatch)
    captured_prompts: list[tuple[str, str]] = []

    def respond(client, *, system_prompt: str, user_prompt: str) -> str:
        captured_prompts.append((system_prompt, user_prompt))
        return json.dumps(_VALID_COPY)

    _make_fake_client(monkeypatch, respond)

    await _summarize()

    _, user_prompt = captured_prompts[0]
    assert "Scene: coffee_shop" in user_prompt
    assert "Role: barista" in user_prompt
    assert "Learner message: I want a latte" in user_prompt
    assert "Feedback JSON:" in user_prompt
    assert "more_natural" in user_prompt


@pytest.mark.anyio
async def test_summarize_retries_invalid_json_then_fails_over_to_fallback(monkeypatch) -> None:
    _configure_live_text_providers(monkeypatch)

    def respond(client, **_) -> str:
        if client.base_url == "https://primary.test":
            return "not-json"
        return json.dumps(_VALID_COPY)

    constructed = _make_fake_client(monkeypatch, respond)

    copy = await _summarize()

    assert copy.next_try == "下一轮试着补一句口味或杯型细节。"
    primary_calls = sum(c.calls for c in constructed if c.base_url == "https://primary.test")
    fallback_calls = sum(c.calls for c in constructed if c.base_url == "https://fallback.test")
    # 解析失败（ValueError 子类）按可重试错误处理：主 provider 初始 1 次 + 重试 1 次，
    # 随后整链切到 fallback 成功。
    assert primary_calls == settings.llm_max_retries_per_provider + 1
    assert fallback_calls == 1


@pytest.mark.anyio
async def test_summarize_raises_model_provider_error_when_all_attempts_fail(monkeypatch) -> None:
    _configure_live_text_providers(monkeypatch)
    _make_fake_client(monkeypatch, lambda client, **_: "not-json")

    with pytest.raises(ModelProviderError):
        await _summarize()


@pytest.mark.anyio
async def test_summarize_passes_review_max_tokens_budget(monkeypatch) -> None:
    _configure_live_text_providers(monkeypatch)
    constructed = _make_fake_client(monkeypatch, lambda client, **_: json.dumps(_VALID_COPY))

    await _summarize()

    assert constructed
    # 复盘输出预算走独立的新配置键，与教练/反馈互不挤占（Finding 10a 同族）。
    assert all(c.max_tokens == settings.llm_review_max_tokens for c in constructed)


@pytest.mark.anyio
async def test_summarize_wires_default_usage_sink(monkeypatch) -> None:
    _configure_live_text_providers(monkeypatch)
    constructed = _make_fake_client(monkeypatch, lambda client, **_: json.dumps(_VALID_COPY))

    await _summarize()

    assert constructed
    # 用量账本在 provider 构造期默认注入：复盘调用成本自动进 llm_usage。
    assert all(c.usage_sink is not None for c in constructed)


def test_review_copy_truncates_overlong_fields_to_cap(caplog) -> None:
    """生产护栏（design 2.3）：超长字段在校验层截到恰上限，截断留 warning 观测日志。

    highlight 用带首尾空白的超长串：截断发生在 strip 之后（after 阶段）。
    """
    with caplog.at_level(logging.WARNING, logger="api.modules.session_engine.review_builder"):
        copy = ReviewCopy.model_validate(
            {
                "scene_title": "咖" * 41,
                "role_label": "店" * 41,
                "highlight": " " + "好" * 121,
                "next_try": "试" * 81,
                "next_step": "步" * 81,
            }
        )

    assert copy.scene_title == "咖" * 40
    assert copy.role_label == "店" * 40
    assert copy.highlight == "好" * 120
    assert copy.next_try == "试" * 80
    assert copy.next_step == "步" * 80
    assert "review_copy_truncated" in caplog.text
    assert "scene_title" in caplog.text


def test_review_copy_keeps_exact_boundary_values() -> None:
    """恰好达界的字段原样通过：截断只发生在超限时（与 REVIEW_PROMPT 软约束逐字段一致）。"""
    fields = {
        "scene_title": "咖" * 40,
        "role_label": "店" * 40,
        "highlight": "好" * 120,
        "next_try": "试" * 80,
        "next_step": "步" * 80,
    }
    copy = ReviewCopy.model_validate(fields)

    for name, value in fields.items():
        assert getattr(copy, name) == value


def test_review_copy_truncation_keeps_other_fields_intact() -> None:
    """单字段超限只截该字段，其余字段原样保留（截断优于整份拒绝的语义）。"""
    copy = ReviewCopy.model_validate({**_VALID_COPY, "next_try": "试" * 81})

    assert copy.next_try == "试" * 80
    assert copy.scene_title == _VALID_COPY["scene_title"]
    assert copy.role_label == _VALID_COPY["role_label"]
    assert copy.highlight == _VALID_COPY["highlight"]
    assert copy.next_step == _VALID_COPY["next_step"]


def test_review_copy_whitespace_only_still_fails_validation() -> None:
    """纯空白仍 ValidationError（strip 前置 + min_length=1）：failover 入口不变。"""
    with pytest.raises(ValidationError):
        ReviewCopy.model_validate({**_VALID_COPY, "highlight": "   "})


def test_review_copy_empty_string_still_fails_validation() -> None:
    """空串仍 ValidationError：min_length=1 语义不变，截断 validator 不放行空值。"""
    with pytest.raises(ValidationError):
        ReviewCopy.model_validate({**_VALID_COPY, "next_step": ""})
