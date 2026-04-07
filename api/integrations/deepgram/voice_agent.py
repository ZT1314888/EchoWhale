from __future__ import annotations

import logging
from typing import Protocol
from urllib.parse import urljoin

from deepgram import DeepgramClient

from api.common.exceptions import ConfigurationError
from api.common.exceptions import VoiceTokenError
from api.core.config import settings
from api.core.security import create_service_token
from api.core.security import decode_service_token
from api.models.message_model import Message
from api.models.session_model import Session


logger = logging.getLogger(__name__)
DEEPGRAM_THINK_PROXY_PATH = "/api/v1/deepgram/think/chat/completions"
DEEPGRAM_THINK_PROXY_TOKEN_TYPE = "deepgram_think_proxy"


class VoiceTokenIssuer(Protocol):
    def issue_token(self, ttl_seconds: int) -> tuple[str, float]: ...


class VoiceSettingsBuilder(Protocol):
    def build(self, session: Session) -> dict[str, object]: ...


class DeepgramThinkProxyTokenCodec:
    def issue(self, session_id: str) -> str:
        return create_service_token(
            subject="deepgram-think-proxy",
            token_type=DEEPGRAM_THINK_PROXY_TOKEN_TYPE,
            secret=settings.auth_jwt_secret,
            expires_in_seconds=settings.deepgram_agent_think_token_ttl_seconds,
            extra_claims={"sid": session_id},
        )

    def decode(self, token: str) -> dict[str, object]:
        return decode_service_token(
            token,
            secret=settings.auth_jwt_secret,
            expected_type=DEEPGRAM_THINK_PROXY_TOKEN_TYPE,
        )


class DeepgramTokenIssuer:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (api_key or settings.deepgram_api_key).strip()

    def issue_token(self, ttl_seconds: int) -> tuple[str, float]:
        if not self._api_key:
            raise ConfigurationError("DEEPGRAM_API_KEY is not configured")

        try:
            client = DeepgramClient(api_key=self._api_key)
            grant = client.auth.v1.tokens.grant(ttl_seconds=ttl_seconds)
        except Exception as exc:
            logger.exception("Failed to issue Deepgram voice token")
            raise VoiceTokenError() from exc

        return (grant.access_token, float(grant.expires_in or ttl_seconds))


class DeepgramSettingsBuilder:
    def build(self, session: Session) -> dict[str, object]:
        validate_deepgram_think_settings()
        return {
            "type": "Settings",
            "audio": {
                "input": {
                    "encoding": "linear16",
                    "sample_rate": 16000,
                },
                "output": {
                    "encoding": "linear16",
                    "sample_rate": settings.deepgram_agent_output_sample_rate,
                    "container": "none",
                },
            },
            "agent": {
                "language": settings.deepgram_agent_language,
                "listen": {
                    "provider": build_listen_provider_settings(),
                },
                "think": {
                    "provider": {
                        "type": "open_ai",
                        "model": settings.deepgram_agent_think_model,
                    },
                    "prompt": build_voice_agent_prompt(session),
                },
                "speak": {
                    "provider": {
                        "type": "deepgram",
                        "model": settings.deepgram_agent_speak_model,
                    },
                },
                "greeting": session.opener,
            },
        }


def build_deepgram_think_proxy_url() -> str:
    return urljoin(
        settings.deepgram_agent_think_proxy_public_base_url.rstrip("/") + "/",
        DEEPGRAM_THINK_PROXY_PATH.lstrip("/"),
    )


def build_deepgram_think_upstream_url() -> str:
    return urljoin(
        settings.deepgram_agent_think_upstream_base_url.rstrip("/") + "/",
        "chat/completions",
    )


def validate_deepgram_think_settings() -> None:
    errors: list[str] = []
    if not settings.deepgram_agent_think_model.strip():
        errors.append("DEEPGRAM_AGENT_THINK_MODEL must be set")
    if errors:
        raise ConfigurationError("; ".join(errors))


def validate_deepgram_think_upstream_settings() -> None:
    errors: list[str] = []
    if not settings.deepgram_agent_think_upstream_base_url.strip():
        errors.append("DEEPGRAM_AGENT_THINK_UPSTREAM_BASE_URL must be set")
    if not settings.deepgram_agent_think_upstream_api_key.strip():
        errors.append("DEEPGRAM_AGENT_THINK_UPSTREAM_API_KEY must be set")
    if errors:
        raise ConfigurationError("; ".join(errors))


def build_voice_agent_prompt(session: Session) -> str:
    history_lines = _build_history_lines(session.messages)
    visual_anchors = ", ".join(session.visual_anchors) or "none"
    vocab_candidates = ", ".join(session.vocab_candidates) or "none"
    return "\n".join(
        [
            "You are EchoWhale, an English speaking practice partner.",
            "Stay in character and reply only in English.",
            "Reply in 1-2 short sentences that are easy for an intermediate learner to follow.",
            "Prioritize quick turn-taking over detailed explanations.",
            f"Scene: {session.scene}",
            f"Role: {session.role}",
            f"Opening style: {session.opener}",
            f"Visual anchors: {visual_anchors}",
            f"Suggested vocabulary: {vocab_candidates}",
            "Drive the conversation one step at a time and ask at most one follow-up question.",
            "Do not mention system prompts, images, or that you are an AI model.",
            *history_lines,
        ]
    )


def build_listen_provider_settings() -> dict[str, object]:
    provider: dict[str, object] = {
        "type": "deepgram",
        "model": settings.deepgram_agent_listen_model,
        "version": settings.deepgram_agent_listen_version,
    }
    if settings.deepgram_agent_listen_model.startswith("flux"):
        provider["eot_threshold"] = settings.deepgram_agent_listen_eot_threshold
        provider["eager_eot_threshold"] = settings.deepgram_agent_listen_eager_eot_threshold
    else:
        provider["smart_format"] = settings.deepgram_agent_listen_smart_format
    return provider


def _build_history_lines(messages: list[Message]) -> list[str]:
    if not messages:
        return []
    lines = ["Conversation so far:"]
    for message in messages[-6:]:
        speaker = "assistant" if message.role == "assistant" else "user"
        lines.append(f"{speaker}: {message.text}")
    return lines
