from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from api.common.exceptions import ConfigurationError
from api.core.config import DEFAULT_JWT_SECRET, NON_PRODUCTION_ENVS, Settings

# 生产清单的"全量合法基线"：每项都满足，供 _production_settings 用 overrides
# 制造单点缺失。字段值只服务测试，不含任何真实凭证。
_PRODUCTION_BASE: dict[str, Any] = {
    "app_env": "production",
    "auth_jwt_secret": "production-secret-0123456789abcdef",
    "auth_cookie_secure": True,
    "allowed_origins": ["https://app.example.com"],
    "frontend_public_base_url": "https://app.example.com",
    "database_url": "postgresql+psycopg://user:pass@db.internal:5432/echowhale",
    "redis_url": "redis://redis.internal:6379/0",
    "model_runtime_mode": "live",
    "r2_endpoint": "https://account-id.r2.cloudflarestorage.com",
    "r2_access_key_id": "r2-access-key",
    "r2_secret_access_key": "r2-secret-key",
    "auth_smtp_host": "smtp.example.com",
    "auth_smtp_username": "noreply@example.com",
    "auth_smtp_password": "smtp-app-password",
    "auth_smtp_from_email": "noreply@example.com",
    "deepgram_api_key": "dg_test_key",
    "deepgram_agent_base_url": "wss://agent.deepgram.com/v1/agent/converse",
    "deepgram_agent_think_model": "gpt-4o-mini",
}


def _production_settings(**overrides: Any) -> Settings:
    """构造一份满足生产清单的 Settings；overrides 用于制造单点缺失。

    `_env_file=None` 屏蔽仓库根目录的 .env，保证用例只受显式传入值影响。
    """
    values: dict[str, Any] = {**_PRODUCTION_BASE, **overrides}
    return Settings(_env_file=None, **values)


# 缺失项矩阵：每项一条——overrides 制造缺失，keyword 为错误信息必须点名的关键词。
# 供生产环境别名 × 缺失项 的全量组合参数化使用。
_MISSING_ITEM_CASES: list[tuple[dict[str, Any], str]] = [
    ({"auth_jwt_secret": DEFAULT_JWT_SECRET}, "AUTH_JWT_SECRET"),
    ({"auth_jwt_secret": ""}, "AUTH_JWT_SECRET"),
    ({"auth_cookie_secure": False}, "AUTH_COOKIE_SECURE"),
    ({"allowed_origins": []}, "ALLOWED_ORIGINS"),
    ({"frontend_public_base_url": "http://localhost:5173"}, "FRONTEND_PUBLIC_BASE_URL"),
    ({"database_url": ""}, "DATABASE_URL"),
    ({"redis_url": ""}, "REDIS_URL"),
    ({"model_runtime_mode": "mock"}, "MODEL_RUNTIME_MODE"),
    ({"r2_endpoint": ""}, "R2_ENDPOINT"),
    ({"r2_access_key_id": ""}, "R2_ACCESS_KEY_ID"),
    ({"r2_secret_access_key": ""}, "R2_SECRET_ACCESS_KEY"),
    ({"auth_smtp_host": ""}, "AUTH_SMTP_HOST"),
    ({"auth_smtp_username": ""}, "AUTH_SMTP_USERNAME"),
    ({"auth_smtp_password": ""}, "AUTH_SMTP_PASSWORD"),
    ({"auth_smtp_from_email": ""}, "AUTH_SMTP_FROM_EMAIL"),
    ({"deepgram_api_key": ""}, "DEEPGRAM_API_KEY"),
    ({"deepgram_agent_base_url": ""}, "DEEPGRAM_AGENT_BASE_URL"),
    ({"deepgram_agent_think_model": ""}, "DEEPGRAM_AGENT_THINK_MODEL"),
]

# 生产判定矩阵：白名单外的值（含 prod/staging/live 拼写偏差与空串）一律按生产校验。
_PRODUCTION_ENV_ALIASES = ["production", "prod", "PROD", "staging", "live", ""]


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


def test_production_settings_require_non_default_auth_secret() -> None:
    settings = _production_settings(auth_jwt_secret=DEFAULT_JWT_SECRET)

    with pytest.raises(ConfigurationError, match="AUTH_JWT_SECRET"):
        settings.validate_runtime()


def test_production_settings_require_secure_auth_cookie() -> None:
    settings = _production_settings(auth_cookie_secure=False)

    with pytest.raises(ConfigurationError, match="AUTH_COOKIE_SECURE"):
        settings.validate_runtime()


def test_production_settings_require_non_empty_allowed_origins() -> None:
    settings = _production_settings(allowed_origins=[])

    with pytest.raises(ConfigurationError, match="ALLOWED_ORIGINS"):
        settings.validate_runtime()


def test_production_settings_require_explicit_frontend_public_base_url() -> None:
    settings = _production_settings(
        frontend_public_base_url="http://localhost:5173",
    )

    with pytest.raises(ConfigurationError, match="FRONTEND_PUBLIC_BASE_URL"):
        settings.validate_runtime()


def test_production_settings_require_deepgram_api_key() -> None:
    settings = _production_settings(deepgram_api_key="")

    with pytest.raises(ConfigurationError, match="DEEPGRAM_API_KEY"):
        settings.validate_runtime()


def test_production_settings_require_deepgram_agent_base_url() -> None:
    settings = _production_settings(deepgram_agent_base_url="")

    with pytest.raises(ConfigurationError, match="DEEPGRAM_AGENT_BASE_URL"):
        settings.validate_runtime()


def test_production_settings_do_not_require_deepgram_think_proxy_settings() -> None:
    # think proxy 三项不在生产清单内：留空必须能通过校验。
    settings = _production_settings(
        deepgram_agent_think_proxy_public_base_url="",
        deepgram_agent_think_upstream_base_url="",
        deepgram_agent_think_upstream_api_key="",
    )

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


def test_mock_model_runtime_does_not_require_live_model_endpoints(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("MODEL_RUNTIME_MODE=mock", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    settings.validate_runtime()


def test_smtp_settings_require_credentials_when_host_is_configured(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "AUTH_SMTP_HOST=smtpdm.aliyun.com",
                "AUTH_SMTP_PORT=465",
                "AUTH_SMTP_USERNAME=",
                "AUTH_SMTP_PASSWORD=",
                "AUTH_SMTP_FROM_EMAIL=",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    with pytest.raises(ConfigurationError, match="AUTH_SMTP_USERNAME"):
        settings.validate_runtime()


def test_smtp_settings_reject_enabling_ssl_and_starttls_together(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "AUTH_SMTP_HOST=smtpdm.aliyun.com",
                "AUTH_SMTP_PORT=465",
                "AUTH_SMTP_USERNAME=noreply@example.com",
                "AUTH_SMTP_PASSWORD=app-password",
                "AUTH_SMTP_FROM_EMAIL=noreply@example.com",
                "AUTH_SMTP_USE_SSL=true",
                "AUTH_SMTP_USE_STARTTLS=true",
            ]
        ),
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    with pytest.raises(ConfigurationError, match="AUTH_SMTP_USE_SSL"):
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


# ---------------------------------------------------------------------------
# 门控反转（fail-closed）矩阵
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env", _PRODUCTION_ENV_ALIASES)
@pytest.mark.parametrize(
    ("overrides", "keyword"),
    _MISSING_ITEM_CASES,
    ids=[keyword for _, keyword in _MISSING_ITEM_CASES],
)
def test_production_gate_fails_closed_on_missing_checklist_item(
    env: str, overrides: dict[str, Any], keyword: str
) -> None:
    # 白名单外的任何 APP_ENV（含空串）都执行生产清单检查，
    # 且错误信息必须点名缺失的那一项。
    settings = _production_settings(app_env=env, **overrides)

    with pytest.raises(ConfigurationError, match=keyword):
        settings.validate_runtime()


@pytest.mark.parametrize("env", sorted(NON_PRODUCTION_ENVS))
def test_non_production_envs_are_exempt_from_production_checklist(env: str) -> None:
    # 白名单环境用默认（空）配置即可启动，不做生产清单检查。
    settings = Settings(_env_file=None, app_env=env)

    settings.validate_runtime()


@pytest.mark.parametrize(
    "secret",
    [
        DEFAULT_JWT_SECRET,  # 等于默认值
        "a" * 29,  # 短于 32 字符
        "",  # 空串
    ],
    ids=["default", "too-short", "empty"],
)
def test_production_rejects_weak_jwt_secret(secret: str) -> None:
    settings = _production_settings(auth_jwt_secret=secret)

    with pytest.raises(ConfigurationError, match="AUTH_JWT_SECRET"):
        settings.validate_runtime()


def test_production_accepts_32_char_jwt_secret() -> None:
    settings = _production_settings(auth_jwt_secret="a" * 32)

    settings.validate_runtime()


def test_production_rejects_mock_model_runtime() -> None:
    # mock 上线即假模型，属于最危险的静默故障；错误信息必须点名 live。
    settings = _production_settings(model_runtime_mode="mock")

    with pytest.raises(ConfigurationError, match="MODEL_RUNTIME_MODE") as exc_info:
        settings.validate_runtime()

    assert "live" in str(exc_info.value)


def test_validate_runtime_logs_effective_mode_without_secret_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _production_settings()

    with caplog.at_level(logging.INFO, logger="api.core.config"):
        settings.validate_runtime()

    assert "app_env=production" in caplog.text
    assert "model_runtime_mode=live" in caplog.text
    # 生效模式日志只打非敏感开关值，不得泄露任何密钥。
    assert _PRODUCTION_BASE["auth_jwt_secret"] not in caplog.text
