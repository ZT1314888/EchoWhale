from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from api.common.exceptions import ConfigurationError


class Settings(BaseSettings):
    app_name: str = "EchoWhale API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    database_url: str = ""
    auth_jwt_secret: str = "dev-secret-change-me"
    auth_access_token_ttl_seconds: int = 900
    auth_refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14
    auth_refresh_cookie_name: str = "echowhale_refresh_token"
    auth_visitor_cookie_name: str = "echowhale_visitor_id"
    auth_cookie_secure: bool = False
    r2_bucket: str = "echo-whale-media"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_endpoint: str = ""
    r2_signed_url_ttl_seconds: int = 900
    media_max_file_size: int = 10 * 1024 * 1024
    media_allowed_content_types: Annotated[list[str], NoDecode] = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]
    llm_provider: str = "mock"
    model_runtime_mode: str = "mock"
    vision_primary_provider: str = "mock"
    vision_primary_base_url: str = ""
    vision_primary_api_key: str = ""
    vision_primary_model: str = ""
    vision_primary_timeout_seconds: int = 30
    vision_fallback_provider: str = "mock"
    vision_fallback_base_url: str = ""
    vision_fallback_api_key: str = ""
    vision_fallback_model: str = ""
    vision_fallback_timeout_seconds: int = 30
    text_primary_provider: str = "mock"
    text_primary_base_url: str = ""
    text_primary_api_key: str = ""
    text_primary_model: str = ""
    text_primary_timeout_seconds: int = 30
    text_fallback_provider: str = "mock"
    text_fallback_base_url: str = ""
    text_fallback_api_key: str = ""
    text_fallback_model: str = ""
    text_fallback_timeout_seconds: int = 30
    deepgram_api_key: str = ""
    deepgram_agent_base_url: str = "wss://api.deepgram.com/v1/agent/converse"
    deepgram_agent_token_ttl_seconds: int = 600
    deepgram_agent_language: str = "en"
    deepgram_agent_listen_model: str = "flux-general-en"
    deepgram_agent_listen_version: str = "v2"
    deepgram_agent_listen_eot_threshold: float = 0.7
    deepgram_agent_listen_eager_eot_threshold: float = 0.4
    deepgram_agent_listen_eot_timeout_ms: int = 6000
    deepgram_agent_listen_smart_format: bool = False
    deepgram_agent_speak_model: str = "aura-2-cordelia-en"
    deepgram_agent_output_sample_rate: int = 24000
    deepgram_agent_think_model: str = ""
    deepgram_agent_think_proxy_public_base_url: str = ""
    deepgram_agent_think_upstream_base_url: str = ""
    deepgram_agent_think_upstream_api_key: str = ""
    deepgram_agent_think_timeout_seconds: int = 30
    deepgram_agent_think_token_ttl_seconds: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("allowed_origins", "media_allowed_content_types", mode="before")
    @classmethod
    def split_csv_values(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def validate_runtime(self) -> None:
        self._validate_model_runtime()

        if self.app_env.lower() != "production":
            return

        errors: list[str] = []
        if self.auth_jwt_secret == "dev-secret-change-me":
            errors.append("AUTH_JWT_SECRET must be explicitly set in production")
        if not self.auth_cookie_secure:
            errors.append("AUTH_COOKIE_SECURE must be true in production")
        if not self.allowed_origins:
            errors.append("ALLOWED_ORIGINS must not be empty in production")
        if not self.deepgram_api_key.strip():
            errors.append("DEEPGRAM_API_KEY must be set in production")
        if not self.deepgram_agent_base_url.strip():
            errors.append("DEEPGRAM_AGENT_BASE_URL must be set in production")
        if not self.deepgram_agent_think_model.strip():
            errors.append("DEEPGRAM_AGENT_THINK_MODEL must be set in production")

        if errors:
            raise ConfigurationError("; ".join(errors))

    def _validate_model_runtime(self) -> None:
        runtime_mode = self.model_runtime_mode.lower()
        if runtime_mode == "mock":
            return
        if runtime_mode != "live":
            raise ConfigurationError("MODEL_RUNTIME_MODE must be either 'mock' or 'live'")

        errors: list[str] = []
        for prefix in (
            "VISION_PRIMARY",
            "VISION_FALLBACK",
            "TEXT_PRIMARY",
            "TEXT_FALLBACK",
        ):
            provider = getattr(self, f"{prefix.lower()}_provider").strip().lower()
            if provider in {"", "mock"}:
                continue

            if not getattr(self, f"{prefix.lower()}_base_url").strip():
                errors.append(f"{prefix}_BASE_URL must be set when {prefix}_PROVIDER is live")
            if not getattr(self, f"{prefix.lower()}_model").strip():
                errors.append(f"{prefix}_MODEL must be set when {prefix}_PROVIDER is live")

        if errors:
            raise ConfigurationError("; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
