from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EchoWhale API"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    default_user_id: str = "demo-user"
    default_user_name: str = "Echo Learner"
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    r2_bucket: str = "echo-whale-media"
    r2_public_base_url: str = "https://cdn.example.com"
    llm_provider: str = "mock"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
