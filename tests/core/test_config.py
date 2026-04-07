from __future__ import annotations

from pathlib import Path

import pytest

from api.common.exceptions import ConfigurationError
from api.core.config import Settings


def test_settings_accept_csv_lists_from_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173",
                "MEDIA_ALLOWED_CONTENT_TYPES=image/jpeg,image/png,image/webp",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert settings.media_allowed_content_types == [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]


def test_settings_support_signed_url_ttl_override(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("R2_SIGNED_URL_TTL_SECONDS=1200", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.r2_signed_url_ttl_seconds == 1200


def test_production_settings_require_non_default_auth_secret(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "AUTH_COOKIE_SECURE=true",
                "ALLOWED_ORIGINS=https://app.example.com",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    with pytest.raises(ConfigurationError, match="AUTH_JWT_SECRET"):
        settings.validate_runtime()


def test_production_settings_require_secure_auth_cookie(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "AUTH_JWT_SECRET=super-secret-for-prod",
                "AUTH_COOKIE_SECURE=false",
                "ALLOWED_ORIGINS=https://app.example.com",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    with pytest.raises(ConfigurationError, match="AUTH_COOKIE_SECURE"):
        settings.validate_runtime()


def test_production_settings_require_non_empty_allowed_origins(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "AUTH_JWT_SECRET=super-secret-for-prod",
                "AUTH_COOKIE_SECURE=true",
                "ALLOWED_ORIGINS=",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    with pytest.raises(ConfigurationError, match="ALLOWED_ORIGINS"):
        settings.validate_runtime()


def test_live_model_runtime_requires_configured_model_endpoints(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "MODEL_RUNTIME_MODE=live",
                "VISION_PRIMARY_PROVIDER=openai_compatible",
                "VISION_PRIMARY_MODEL=qwen-vl-max",
                "TEXT_PRIMARY_PROVIDER=openai_compatible",
                "TEXT_PRIMARY_MODEL=qwen-max",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    with pytest.raises(ConfigurationError, match="VISION_PRIMARY_BASE_URL"):
        settings.validate_runtime()


def test_production_settings_require_deepgram_api_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "AUTH_JWT_SECRET=super-secret-for-prod",
                "AUTH_COOKIE_SECURE=true",
                "ALLOWED_ORIGINS=https://app.example.com",
                "DEEPGRAM_API_KEY=",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    with pytest.raises(ConfigurationError, match="DEEPGRAM_API_KEY"):
        settings.validate_runtime()


def test_production_settings_require_deepgram_agent_base_url(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "AUTH_JWT_SECRET=super-secret-for-prod",
                "AUTH_COOKIE_SECURE=true",
                "ALLOWED_ORIGINS=https://app.example.com",
                "DEEPGRAM_API_KEY=dg_test_key",
                "DEEPGRAM_AGENT_BASE_URL=",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    with pytest.raises(ConfigurationError, match="DEEPGRAM_AGENT_BASE_URL"):
        settings.validate_runtime()


def test_production_settings_do_not_require_deepgram_think_proxy_settings(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "APP_ENV=production",
                "AUTH_JWT_SECRET=super-secret-for-prod",
                "AUTH_COOKIE_SECURE=true",
                "ALLOWED_ORIGINS=https://app.example.com",
                "DEEPGRAM_API_KEY=dg_test_key",
                "DEEPGRAM_AGENT_BASE_URL=wss://agent.deepgram.com/v1/agent/converse",
                "DEEPGRAM_AGENT_THINK_MODEL=gpt-4o-mini",
                "DEEPGRAM_AGENT_THINK_PROXY_PUBLIC_BASE_URL=",
                "DEEPGRAM_AGENT_THINK_UPSTREAM_BASE_URL=",
                "DEEPGRAM_AGENT_THINK_UPSTREAM_API_KEY=",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    settings.validate_runtime()


def test_settings_support_deepgram_latency_tuning_overrides(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DEEPGRAM_AGENT_LISTEN_EOT_THRESHOLD=0.75",
                "DEEPGRAM_AGENT_LISTEN_EAGER_EOT_THRESHOLD=0.45",
                "DEEPGRAM_AGENT_LISTEN_EOT_TIMEOUT_MS=5000",
                "DEEPGRAM_AGENT_LISTEN_SMART_FORMAT=true",
                "DEEPGRAM_AGENT_OUTPUT_SAMPLE_RATE=16000",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.deepgram_agent_listen_eot_threshold == 0.75
    assert settings.deepgram_agent_listen_eager_eot_threshold == 0.45
    assert settings.deepgram_agent_listen_eot_timeout_ms == 5000
    assert settings.deepgram_agent_listen_smart_format is True
    assert settings.deepgram_agent_output_sample_rate == 16000


def test_mock_model_runtime_does_not_require_live_model_endpoints(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MODEL_RUNTIME_MODE=mock", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    settings.validate_runtime()
